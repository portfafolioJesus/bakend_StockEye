"""Postproceso del % de vacío y presupuesto de tiempo del modelo real."""
import os
import time
from pathlib import Path

import numpy as np
import pytest

from stockeye.inferencia.postproceso import Parametros, analizar, anotar
from stockeye.inferencia.segformer_onnx import tamano_trabajo

MODELO = Path(__file__).resolve().parents[1] / "modelos" / "segformer-mit-b1-v1.onnx"


def prob(mapa: np.ndarray) -> np.ndarray:
    """Mapa de clases → probabilidades one-hot (H, W, 3)."""
    return np.eye(3, dtype=np.float32)[mapa]


def test_porcentaje_ignora_el_fondo():
    mapa = np.zeros((100, 200), np.int64)       # fondo
    mapa[20:80, 20:180] = 1                      # góndola ocupada: 60 × 160 = 9600 px
    mapa[30:50, 40:80] = 2                       # vacío 20 × 40 = 800 px
    r = analizar(prob(mapa), np.zeros((100, 200, 3), np.uint8), Parametros())
    assert r["pct"] == pytest.approx(100 * 800 / 9600, abs=0.01)
    assert r["estado"] == "medida"
    assert len(r["regiones"]) == 1
    caja = r["regiones"][0]
    assert (caja.x_min, caja.y_min) == pytest.approx((0.2, 0.3))


def test_sin_gondola():
    r = analizar(prob(np.zeros((50, 50), np.int64)), np.zeros((50, 50, 3), np.uint8), Parametros())
    assert r["pct"] == 0 and r["estado"] == "sin_gondola"


def test_anotada_es_jpeg():
    mapa = np.ones((60, 80), np.int64); mapa[10:30, 10:30] = 2
    r = analizar(prob(mapa), np.zeros((60, 80, 3), np.uint8), Parametros())
    assert anotar(np.zeros((60, 80, 3), np.uint8), r["mascara_vacio"], r["regiones"])[:2] == b"\xff\xd8"


@pytest.mark.parametrize("alto,ancho", [(1080, 1920), (3000, 4000), (1920, 1080)])
def test_tope_de_pixeles_independiente_de_la_proporcion(alto, ancho):
    h, w = tamano_trabajo(alto, ancho, 1280, 740_000)
    assert h % 32 == 0 and w % 32 == 0 and h * w <= 740_000 * 1.08 and max(h, w) <= 1280


@pytest.mark.skipif(not MODELO.is_file(), reason="Falta el modelo ONNX (ejecuta herramientas/empaquetar_modelo.py)")
def test_modelo_real_cumple_presupuesto_de_3_segundos():
    import cv2
    from stockeye.inferencia.segformer_onnx import MotorSegFormerOnnx
    motor = MotorSegFormerOnnx(MODELO, pixeles_max=740_000, hilos=int(os.environ.get("ORT_HILOS", 2)))
    img = np.random.default_rng(0).integers(0, 255, (3000, 4000, 3), dtype=np.uint8)
    datos = cv2.imencode(".jpg", img)[1].tobytes()
    tiempos = []
    for _ in range(3):
        t = time.perf_counter()
        r = motor.inferir_bytes(datos)
        tiempos.append(time.perf_counter() - t)
    assert 0 <= r.porcentaje_vacio <= 100
    assert max(tiempos) < 3.0, tiempos
