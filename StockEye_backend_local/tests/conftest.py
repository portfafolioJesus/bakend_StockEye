from dataclasses import replace
from pathlib import Path
import os

import numpy as np
from PIL import Image, ImageOps
import pytest

from stockeye.configuracion import Configuracion
from stockeye.motor import Prediccion


@pytest.fixture(scope="session")
def postgres_test_dsn():
    dsn = os.environ.get("STOCKEYE_TEST_DATABASE_URL")
    if not dsn:
        pytest.skip("Defina STOCKEYE_TEST_DATABASE_URL para la base aislada stockeye_test.")
    import psycopg
    from stockeye.registro import Registro
    from migrar_postgres import preparar_esquema
    with psycopg.connect(dsn) as db:
        nombre = db.execute("SELECT current_database()").fetchone()[0]
        if nombre != "stockeye_test":
            pytest.fail("Las pruebas destructivas solo admiten la base exacta stockeye_test.")
    registro = Registro(dsn)
    registro.adquirir_instancia()
    try:
        preparar_esquema(registro, Path(__file__).resolve().parents[1] / "migraciones")
    finally:
        registro.liberar_instancia()
    return dsn


@pytest.fixture
def cfg(tmp_path, postgres_test_dsn):
    from stockeye.registro import Registro
    registro = Registro(postgres_test_dsn)
    registro.adquirir_instancia()
    try:
        with registro.conexion() as db:
            nombre = db.execute("SELECT current_database() AS nombre").fetchone()["nombre"]
            if nombre != "stockeye_test":
                pytest.fail("No se permite limpiar una base diferente de stockeye_test.")
            db.execute("TRUNCATE TABLE public.trabajos, public.observaciones RESTART IDENTITY")
    finally:
        registro.liberar_instancia()
    configuracion = Configuracion.model_validate({
        "carpetas": {1: tmp_path / "entrada1", 2: tmp_path / "entrada2"},
        "datos": tmp_path / "datos", "modelo": {"archivo": tmp_path / "modelos" / "modelo.pt"},
        "revision_segundos": 30, "estabilidad_segundos": 2,
        "base_datos": {"dsn": postgres_test_dsn, "variable_entorno": "STOCKEYE_TEST_DATABASE_URL"},
    })
    configuracion.crear_carpetas()
    return configuracion


def foto(ruta: Path, color=(120, 80, 60)):
    Image.new("RGB", (96, 64), color).save(ruta)
    return ruta


class MotorPrueba:
    """Doble de prueba explícito: nunca se distribuye como motor de la aplicación."""
    version = "prueba-controlada"
    dispositivo = "cpu"

    def __init__(self, cfg):
        self.llamadas = 0

    def inferir(self, ruta):
        self.llamadas += 1
        rgb = np.asarray(ImageOps.exif_transpose(Image.open(ruta)).convert("RGB")).copy()
        mapa = np.ones(rgb.shape[:2], dtype=np.uint8)
        mapa[10:20, 10:30] = 2
        gondola = {"id_local": 1, "estado": "parcial", "pct_vacio_observado": 24.05,
            "pct_vacio_gondola_completa": None, "cantidad_regiones_vacias": 1, "semaforo": "revisar"}
        return Prediccion(rgb, mapa, [gondola], "parcial", .01, self.version, "a" * 64,
                          {"modo": "completa", "umbral_vacio": .5}, {})


def encolar(servicio, tiempo=100):
    servicio.revisor.revisar(tiempo)
    return servicio.revisor.revisar(tiempo + 30)
