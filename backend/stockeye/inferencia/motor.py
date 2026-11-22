"""Interfaz común de los motores de inferencia.

Cada familia de modelo (SegFormer exportado a ONNX, YOLO, ...) implementa
`MotorVacio`. El worker solo conoce esta interfaz, así que cambiar de modelo
no toca la cola ni la base de datos.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

import numpy as np


@dataclass(frozen=True)
class Region:
    """Caja normalizada 0..1 (lo que se guarda en la tabla `deteccion`)."""
    clase: str
    confianza: float
    x_min: float
    y_min: float
    x_max: float
    y_max: float


@dataclass
class Resultado:
    porcentaje_vacio: float
    regiones: list[Region]
    num_vacios: int
    num_productos: int
    anotada_jpg: bytes
    ancho_px: int
    alto_px: int
    ms_inferencia: int
    estado_medicion: str  # medida | parcial | sin_gondola
    detalle: dict = field(default_factory=dict)


class MotorVacio(Protocol):
    familia: str
    descripcion: str

    def inferir(self, imagen_bgr: np.ndarray, roi: list | None = None) -> Resultado: ...

    def inferir_bytes(self, datos: bytes, roi: list | None = None,
                      tamano_original: tuple[int, int] | None = None) -> Resultado: ...


def recortar_roi(imagen_bgr: np.ndarray, roi: list | None) -> np.ndarray:
    """Recorta al rectángulo envolvente de una ROI normalizada [[x, y], ...]."""
    if not roi:
        return imagen_bgr
    puntos = np.asarray(roi, dtype=float)
    if puntos.ndim != 2 or puntos.shape[1] != 2 or len(puntos) < 3:
        return imagen_bgr
    alto, ancho = imagen_bgr.shape[:2]
    x0, y0 = np.clip(puntos.min(0), 0, 1)
    x1, y1 = np.clip(puntos.max(0), 0, 1)
    if x1 - x0 < 0.05 or y1 - y0 < 0.05:
        return imagen_bgr
    return imagen_bgr[int(y0 * alto):int(np.ceil(y1 * alto)), int(x0 * ancho):int(np.ceil(x1 * ancho))]
