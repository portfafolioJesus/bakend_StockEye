"""Fixtures. Requiere PostgreSQL 16 (el del docker-compose sirve):

    STOCKEYE_TEST_DATABASE_URL=postgresql://stockeye:<clave>@localhost:5433/stockeye_test pytest -q

Por seguridad solo corre contra una BD cuyo nombre termine en _test. Cada
test parte de una copia limpia (CREATE DATABASE ... TEMPLATE) con el seed.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from urllib.parse import urlparse, urlunparse

import psycopg
import pytest

RAIZ = Path(__file__).resolve().parents[1]
DSN = os.environ.get("STOCKEYE_TEST_DATABASE_URL", "postgresql://stockeye:prueba@localhost:5433/stockeye_test")
NOMBRE = urlparse(DSN).path.lstrip("/")
PLANTILLA = NOMBRE + "_plantilla"
if not NOMBRE.endswith("_test"):
    raise SystemExit("STOCKEYE_TEST_DATABASE_URL debe apuntar a una BD *_test (se borra en cada test)")


def _dsn(db: str) -> str:
    u = urlparse(DSN)
    return urlunparse(u._replace(path="/" + db))


def _admin():
    return psycopg.connect(_dsn("postgres"), autocommit=True)


@pytest.fixture(scope="session", autouse=True)
def entorno(tmp_path_factory):
    datos = tmp_path_factory.mktemp("datos")
    os.environ.update(DATABASE_URL=DSN, DATOS_DIR=str(datos), MODELOS_DIR=str(RAIZ / "modelos"), AUTO_MIGRAR="false",
                      JWT_SECRETO="test-" + "x" * 40, GROQ_API_KEY="", FCM_CREDENCIALES="", VAPID_PRIVADA="")
    from stockeye.core import almacenamiento, config, migraciones
    config.ajustes.cache_clear()
    almacenamiento._almacen = None
    try:
        with _admin() as c:
            c.execute(f'DROP DATABASE IF EXISTS "{PLANTILLA}" WITH (FORCE)')
            c.execute(f'CREATE DATABASE "{PLANTILLA}"')
    except psycopg.OperationalError as e:
        pytest.skip(f"PostgreSQL de pruebas no disponible: {e}", allow_module_level=True)
    migraciones.aplicar(_dsn(PLANTILLA), config.ajustes().db_dir)
    migraciones.sembrar_demo(_dsn(PLANTILLA), config.ajustes().db_dir)
    yield datos


@pytest.fixture(autouse=True)
def bd(entorno):
    with _admin() as c:
        c.execute(f'DROP DATABASE IF EXISTS "{NOMBRE}" WITH (FORCE)')
        c.execute(f'CREATE DATABASE "{NOMBRE}" TEMPLATE "{PLANTILLA}"')
    yield DSN


@pytest.fixture
def conn(bd):
    with psycopg.connect(bd, autocommit=True, row_factory=psycopg.rows.dict_row) as c:
        yield c


@pytest.fixture
def cliente(bd):
    from fastapi.testclient import TestClient
    from stockeye.api.main import crear_app
    with TestClient(crear_app()) as c:
        yield c


def token(cliente, email: str) -> dict:
    r = cliente.post("/api/v1/auth/login", json={"email": email, "clave": "StockEye2026!"})
    assert r.status_code == 200, r.text
    return {"Authorization": "Bearer " + r.json()["acceso"]}


def jpg(ancho=640, alto=360) -> bytes:
    import cv2
    import numpy as np
    img = np.full((alto, ancho, 3), 90, np.uint8)
    cv2.rectangle(img, (20, 20), (ancho - 20, alto - 20), (40, 160, 220), -1)
    return cv2.imencode(".jpg", img)[1].tobytes()


class MotorFalso:
    """Devuelve el % que se le indique (para probar las reglas sin el modelo real)."""
    familia = "SEGFORMER"
    descripcion = "falso"

    def __init__(self, pct: float = 20.0):
        self.pct = pct

    def inferir_bytes(self, datos, roi=None, tamano_original=None):
        from stockeye.inferencia.motor import Region, Resultado
        return Resultado(porcentaje_vacio=self.pct, num_vacios=1, num_productos=0, anotada_jpg=datos,
                         regiones=[Region("vacio", 0.9, 0.1, 0.2, 0.3, 0.5)], ancho_px=640, alto_px=360,
                         ms_inferencia=5, estado_medicion="medida")


@pytest.fixture
def worker(bd):
    from stockeye.core.config import ajustes
    from stockeye.inferencia.worker import WorkerInferencia
    creados = []

    def fabricar(pct=20.0, nombre="w1", recintos="*"):
        a = ajustes().model_copy(update={"worker_nombre": nombre, "worker_recintos": recintos})
        motor = MotorFalso(pct)
        w = WorkerInferencia(a, fabrica_motor=lambda m, a: motor)
        w.cargar_modelo()
        w.motor_falso = motor
        creados.append(w)
        return w
    yield fabricar
    for w in creados:
        w.conn.close()
        w.escucha.close()


def procesar_todo(w) -> int:
    n = 0
    while img := w.tomar():
        w.procesar_seguro(img)
        n += 1
    return n


sys.modules.setdefault("conftest_ayuda", sys.modules[__name__])
