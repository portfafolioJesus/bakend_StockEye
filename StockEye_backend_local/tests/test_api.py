import json
from pathlib import Path
import threading
import time

from fastapi.testclient import TestClient
import numpy as np
from PIL import Image
import pytest

from stockeye.api import crear_app
from stockeye.procesador import Servicio
from .conftest import MotorPrueba, encolar, foto


@pytest.fixture
def terminado(cfg):
    s = Servicio(cfg, MotorPrueba)
    for n in (1, 2): foto(cfg.carpetas[n] / "foto.png")
    encolar(s); s.cargar_motor()
    while s.procesar_uno(): pass
    return s


def test_lista_filtra_sucursal_y_es_compatible_con_android(cfg, terminado):
    with TestClient(crear_app(cfg, iniciar_servicios=False)) as cliente:
        r = cliente.get("/api/imagenes?sucursal_id=1")
        assert r.status_code == 200 and r.headers["X-Total-Count"] == "1"
        fila = r.json()[0]
        assert fila["sucursal_id"] == 1 and fila["sucursal"] == "Sucursal 1"
        assert {"id", "nombre", "imagenUrl", "actualizadaEn"} <= fila.keys()
        assert cliente.get(fila["imagenUrl"]).headers["content-type"].startswith("image/jpeg")
        assert len(cliente.get("/api/imagenes").json()) == 2


def test_detalle_conserva_parcial_null_y_regiones(cfg, terminado):
    with TestClient(crear_app(cfg, iniciar_servicios=False)) as cliente:
        ident = cliente.get("/api/imagenes").json()[0]["id"]
        d = cliente.get(f"/api/analisis/{ident}").json()
        assert d["estado_medicion"] == "parcial"
        assert d["gondolas"][0]["pct_vacio_gondola_completa"] is None
        assert d["gondolas"][0]["pct_vacio_observado"] == 24.05
        assert d["gondolas"][0]["semaforo"] == "revisar"
        assert cliente.get(d["urls"]["mascara"]).headers["content-type"].startswith("image/png")


def test_original_identico_y_mascara_correcta(cfg, terminado):
    with TestClient(crear_app(cfg, iniciar_servicios=False)) as cliente:
        fila = cliente.get("/api/imagenes?sucursal_id=1").json()[0]
        raw = cliente.get(f"/api/imagenes/{fila['id']}/original").content
        assert raw == (cfg.carpetas[1] / "foto.png").read_bytes()
        mask = np.asarray(Image.open(terminado.archivos.archivo(fila["id"], "mascara")))
        assert set(np.unique(mask)) == {1, 2}


def test_marcado_resalta_vacio_y_conserva_ocupado(cfg, terminado):
    trabajo = terminado.registro.listar()[0][0]
    img = np.asarray(Image.open(terminado.archivos.archivo(trabajo["id"], "superpuesta")))
    assert np.max(np.abs(img[45, 70].astype(int) - [120, 80, 60])) < 6
    assert img[15, 20, 0] > img[45, 70, 0] + 40


@pytest.mark.parametrize("consulta", ["sucursal_id=3", "sucursal_id=0", "limite=0", "desde=-1"])
def test_parametros_invalidos(cfg, consulta):
    with TestClient(crear_app(cfg, iniciar_servicios=False)) as cliente:
        assert cliente.get("/api/imagenes?" + consulta).status_code == 422


def test_paginacion_y_get_no_reanaliza(cfg, terminado):
    with TestClient(crear_app(cfg, iniciar_servicios=False)) as cliente:
        a = cliente.get("/api/imagenes?limite=1").json()
        b = cliente.get("/api/imagenes?limite=1&desde=1").json()
        assert a[0]["id"] != b[0]["id"]
        for _ in range(4): assert cliente.get("/api/imagenes").status_code == 200
        assert terminado.motor.llamadas == 2
        assert cliente.get("/api/trabajos?estado=completada").json()["total"] == 2


def test_ids_desconocidos_y_metodos_no_definidos(cfg):
    with TestClient(crear_app(cfg, iniciar_servicios=False)) as cliente:
        assert cliente.get("/api/analisis/incorrecto").status_code == 404
        assert cliente.get("/api/analisis/" + "a" * 32).status_code == 404
        assert cliente.post("/api/imagenes", json={}).status_code == 405


def test_documento_corrupto_se_informa_sin_inventar_resultados(cfg, terminado):
    trabajo = terminado.registro.listar()[0][0]
    (terminado.archivos.carpeta(trabajo["id"]) / "resultado.json").write_text("{roto")
    with TestClient(crear_app(cfg, iniciar_servicios=False)) as cliente:
        assert cliente.get("/api/imagenes").status_code == 503


def test_archivo_fuera_del_analisis_no_se_sirve(cfg, terminado):
    trabajo = terminado.registro.listar()[0][0]
    p = terminado.archivos.carpeta(trabajo["id"]) / "resultado.json"
    d = json.loads(p.read_text()); d["archivos"]["original"] = "../../config.json"
    p.write_text(json.dumps(d))
    with TestClient(crear_app(cfg, iniciar_servicios=False)) as cliente:
        assert cliente.get(f"/api/imagenes/{trabajo['id']}/original").status_code == 404


def test_api_sigue_respondiendo_durante_inferencia(cfg):
    inicio, continuar = threading.Event(), threading.Event()
    class MotorLento(MotorPrueba):
        def inferir(self, ruta):
            inicio.set()
            assert continuar.wait(8)
            return super().inferir(ruta)
    s = Servicio(cfg, MotorPrueba)
    foto(cfg.carpetas[1] / "foto.png"); encolar(s)
    app = crear_app(cfg, motor_factory=MotorLento)
    with TestClient(app) as cliente:
        try:
            assert inicio.wait(5)
            r = cliente.get("/health")
            assert r.status_code == 200 and r.json()["cola"]["procesando"] == 1
            foto(cfg.carpetas[2] / "nueva.png")
            servicio = app.state.servicio
            servicio.revisor.revisar(500); assert servicio.revisor.revisar(530) == 1
            assert cliente.get("/health").json()["cola"]["pendiente"] == 1
        finally: continuar.set()


def test_arranca_sin_pt_y_explica_modelo_no_disponible(cfg):
    with TestClient(crear_app(cfg)) as cliente:
        limite = time.monotonic() + 3
        while time.monotonic() < limite:
            salud = cliente.get("/health").json()
            if salud["modelo"]["error"]: break
            time.sleep(.02)
        assert salud["status"] == "ok" and not salud["modelo"]["disponible"]
        assert "modelo.pt" in salud["modelo"]["error"]
        assert cliente.get("/api/imagenes").json() == []
