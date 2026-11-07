from dataclasses import replace
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps
import pytest

from stockeye.configuracion import Configuracion
from stockeye.motor import Prediccion


@pytest.fixture
def cfg(tmp_path):
    configuracion = Configuracion.model_validate({
        "carpetas": {1: tmp_path / "entrada1", 2: tmp_path / "entrada2"},
        "datos": tmp_path / "datos", "modelo": {"archivo": tmp_path / "modelos" / "modelo.pt"},
        "revision_segundos": 30, "estabilidad_segundos": 2,
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
