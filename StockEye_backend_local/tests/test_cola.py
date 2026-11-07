from pathlib import Path
import time

import pytest

from stockeye.instancia import InstanciaUnica
from stockeye.procesador import EntradaInestable, Servicio
from .conftest import MotorPrueba, encolar, foto


def test_doscientas_imagenes_se_encolan_una_vez_y_el_procesador_toma_una(cfg):
    for sucursal in (1, 2):
        for i in range(100): foto(cfg.carpetas[sucursal] / f"{i:03}.png")
    s = Servicio(cfg, MotorPrueba)
    assert s.revisor.revisar(100) == 0
    assert s.revisor.revisar(130) == 200
    assert s.revisor.revisar(160) == 0
    assert s.registro.conteos()["pendiente"] == 200
    s.cargar_motor()
    assert s.procesar_uno()
    assert s.registro.conteos() == {"pendiente": 199, "procesando": 0, "completada": 1, "error": 0}
    assert s.motor.llamadas == 1


def test_nombre_igual_en_ambas_sucursales_y_persistencia(cfg):
    for n in (1, 2): foto(cfg.carpetas[n] / "foto.png")
    s = Servicio(cfg, MotorPrueba)
    assert encolar(s) == 2
    otro = Servicio(cfg, MotorPrueba)
    assert otro.revisor.revisar(190) == 0
    filas, total = otro.registro.listar()
    assert total == 2 and {f["sucursal_id"] for f in filas} == {1, 2}
    assert len({f["id"] for f in filas}) == 2


def test_copia_inmutable_si_se_sobrescribe_entrada(cfg):
    ruta = foto(cfg.carpetas[1] / "foto.png")
    original = ruta.read_bytes()
    s = Servicio(cfg, MotorPrueba)
    encolar(s)
    foto(ruta, (0, 0, 255))
    s.cargar_motor(); s.procesar_uno()
    trabajo = s.registro.listar()[0][0]
    assert s.archivos.archivo(trabajo["id"], "original").read_bytes() == original
    assert encolar(s, 200) == 1
    assert s.registro.conteos()["pendiente"] == 1


def test_archivo_que_cambia_reinicia_confirmacion(cfg):
    ruta = foto(cfg.carpetas[1] / "foto.png")
    s = Servicio(cfg, MotorPrueba)
    assert s.revisor.revisar(100) == 0
    foto(ruta, (0, 0, 255))
    assert s.revisor.revisar(130) == 0
    assert s.revisor.revisar(160) == 1


def test_cambio_durante_copia_no_deja_temporales(cfg):
    ruta = foto(cfg.carpetas[1] / "foto.png")
    antes = ruta.stat()
    foto(ruta, (0, 255, 0))
    s = Servicio(cfg, MotorPrueba)
    with pytest.raises(EntradaInestable):
        s.revisor._copiar(ruta, cfg.temporales / "prueba.png", antes)
    assert list(cfg.temporales.iterdir()) == []


def test_temporales_vacios_y_subcarpetas_no_se_procesan(cfg):
    (cfg.carpetas[1] / "vacia.png").write_bytes(b"")
    (cfg.carpetas[1] / "parcial.jpg.tmp").write_bytes(b"parcial")
    sub = cfg.carpetas[1] / "otra"; sub.mkdir(); foto(sub / "foto.png")
    s = Servicio(cfg, MotorPrueba)
    assert encolar(s) == 0


def test_exceso_tamano_se_registra_una_vez(cfg):
    cfg.limites.max_archivo_mb = .00001
    foto(cfg.carpetas[1] / "grande.png")
    s = Servicio(cfg, MotorPrueba)
    encolar(s)
    assert s.registro.conteos()["error"] == 1
    s.revisor.revisar(160)
    assert s.registro.listar()[1] == 1
    assert list(cfg.temporales.iterdir()) == []


def test_error_no_impide_siguiente_imagen(cfg):
    (cfg.carpetas[1] / "rota.jpg").write_bytes(b"no es una imagen")
    foto(cfg.carpetas[1] / "buena.png")
    s = Servicio(cfg, MotorPrueba); encolar(s); s.cargar_motor()
    assert s.procesar_uno() and s.procesar_uno()
    assert s.registro.conteos()["error"] == 1
    assert s.registro.conteos()["completada"] == 1


def test_fifo_y_recuperacion_de_interrumpidos(cfg):
    foto(cfg.carpetas[1] / "primera.png")
    s = Servicio(cfg, MotorPrueba); encolar(s)
    primero = s.registro.tomar()
    foto(cfg.carpetas[2] / "segunda.png"); encolar(s, 200)
    nuevo = Servicio(cfg, MotorPrueba)
    nuevo.iniciar(ejecutar_hilos=False)
    try:
        recuperado = nuevo.registro.tomar()
        assert recuperado["id"] == primero["id"]
        assert recuperado["intentos"] == 2
    finally: nuevo.detener()


def test_resultado_confirmado_en_disco_se_recupera_sin_reinferir(cfg):
    foto(cfg.carpetas[1] / "foto.png")
    s = Servicio(cfg, MotorPrueba); encolar(s); s.cargar_motor()
    trabajo = s.registro.tomar()
    prediccion = s.motor.inferir(Path(trabajo["copia"]))
    s.archivos.guardar(trabajo, Path(trabajo["copia"]), prediccion)
    # Simula caída entre el renombrado atómico de archivos y la confirmación SQLite.
    nuevo = Servicio(cfg, MotorPrueba); nuevo.iniciar(ejecutar_hilos=False)
    try:
        nuevo.cargar_motor(); nuevo.procesar_uno()
        assert nuevo.motor.llamadas == 0
        assert nuevo.registro.conteos()["completada"] == 1
    finally: nuevo.detener()


def test_no_modelo_conserva_pendientes(cfg):
    foto(cfg.carpetas[1] / "foto.png")
    s = Servicio(cfg); encolar(s); s.cargar_motor()
    assert not s.procesar_uno()
    assert s.registro.conteos()["pendiente"] == 1
    assert s.error_modelo and s.motor is None


def test_segunda_instancia_rechazada_y_liberacion_correcta(cfg):
    a, b = InstanciaUnica(cfg.datos / "lock"), InstanciaUnica(cfg.datos / "lock")
    a.adquirir()
    try:
        with pytest.raises(RuntimeError): b.adquirir()
    finally: a.liberar()
    b.adquirir(); b.liberar()


def test_reintento_de_error_conserva_identificador(cfg):
    foto(cfg.carpetas[1] / "foto.png")
    s = Servicio(cfg, MotorPrueba); encolar(s)
    trabajo = s.registro.tomar(); s.registro.terminar(trabajo["id"], "Fallo temporal")
    assert s.registro.reintentar_errores() == 1
    s.cargar_motor(); s.procesar_uno()
    assert s.registro.obtener(trabajo["id"])["estado"] == "completada"


def test_fallo_de_limpieza_no_convierte_exito_en_error(cfg, monkeypatch):
    foto(cfg.carpetas[1] / "foto.png")
    s = Servicio(cfg, MotorPrueba); encolar(s); s.cargar_motor()
    unlink = Path.unlink
    def negar_copia(self, *args, **kwargs):
        if self.parent == cfg.temporales and self.suffix == ".png":
            raise PermissionError("Archivo temporal ocupado")
        return unlink(self, *args, **kwargs)
    monkeypatch.setattr(Path, "unlink", negar_copia)
    s.procesar_uno()
    assert s.registro.conteos()["completada"] == 1
    assert s.registro.conteos()["error"] == 0
