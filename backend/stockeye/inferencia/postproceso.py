"""Del mapa de probabilidades de SegFormer al % de vacío, cajas e imagen anotada.

Port de `StockEye_backend_local/stockeye/inferencia_base` (`mapa_desde_prob`,
`gondolas_desde_mapa`), simplificado para correr en < 100 ms en CPU:
  * clases 0=fondo, 1=ocupado, 2=vacío;
  * un píxel es "evidencia de góndola" si es ocupado o vacío;
  * se descartan componentes de góndola chicos (ruido);
  * % vacío = |vacío ∩ evidencia| / |evidencia| (el fondo no cuenta).
El cálculo se hace a la resolución de trabajo de la red: el % es una
proporción, así que no cambia de forma apreciable respecto a la original.
"""
from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

from .motor import Region

FONDO, OCUPADO, VACIO = 0, 1, 2
COLOR_VACIO = (16, 94, 234)       # BGR, naranjo del mockup (#EA5E10)
COLOR_TEXTO = (255, 255, 255)


@dataclass(frozen=True)
class Parametros:
    umbral_vacio: float = 0.5        # p(vacío) mínima para marcar un píxel como vacío
    area_min_gondola: float = 0.01   # fracción de la imagen
    area_min_caja: float = 0.002     # fracción de la imagen para dibujar/contar un vacío
    margen_borde_px: int = 3

    @classmethod
    def desde_dict(cls, datos: dict | None, umbral: float | None = None) -> "Parametros":
        datos = dict(datos or {})
        if umbral is not None:
            datos["umbral_vacio"] = float(umbral)
        conocidos = {k: datos[k] for k in cls.__dataclass_fields__ if k in datos}
        p = cls(**conocidos)
        if not 0 < p.umbral_vacio < 1:
            raise ValueError("umbral_vacio debe estar entre 0 y 1")
        return p


def softmax_canales(logits_hwc: np.ndarray) -> np.ndarray:
    m = logits_hwc.max(axis=2, keepdims=True)
    e = np.exp(logits_hwc - m, dtype=np.float32)
    return e / e.sum(axis=2, keepdims=True)


def analizar(prob_hwc: np.ndarray, imagen_bgr: np.ndarray, p: Parametros) -> dict:
    """prob_hwc: (H, W, 3) a la misma resolución que imagen_bgr."""
    alto, ancho = prob_hwc.shape[:2]
    total = alto * ancho
    ocupado = prob_hwc[..., OCUPADO] > prob_hwc[..., FONDO]
    vacio = prob_hwc[..., VACIO] >= p.umbral_vacio
    base = (ocupado | vacio).astype(np.uint8)

    n, etiquetas, stats, _ = cv2.connectedComponentsWithStats(base, connectivity=8)
    validas = [i for i in range(1, n) if stats[i, cv2.CC_STAT_AREA] >= p.area_min_gondola * total]
    if not validas:
        return dict(pct=0.0, regiones=[], estado="sin_gondola", mascara_vacio=np.zeros_like(vacio))

    evidencia = np.isin(etiquetas, validas)
    b = p.margen_borde_px
    parcial = any(
        stats[i, cv2.CC_STAT_LEFT] <= b or stats[i, cv2.CC_STAT_TOP] <= b
        or stats[i, cv2.CC_STAT_LEFT] + stats[i, cv2.CC_STAT_WIDTH] >= ancho - b
        or stats[i, cv2.CC_STAT_TOP] + stats[i, cv2.CC_STAT_HEIGHT] >= alto - b
        for i in validas
    )
    vacio_ev = vacio & evidencia
    pct = 100.0 * np.count_nonzero(vacio_ev) / max(1, np.count_nonzero(evidencia))

    regiones: list[Region] = []
    nv, etq_v, stats_v, _ = cv2.connectedComponentsWithStats(vacio_ev.astype(np.uint8), connectivity=8)
    prob_v = prob_hwc[..., VACIO]
    for i in range(1, nv):
        if stats_v[i, cv2.CC_STAT_AREA] < p.area_min_caja * total:
            continue
        x, y, w, h = (int(stats_v[i, k]) for k in (cv2.CC_STAT_LEFT, cv2.CC_STAT_TOP, cv2.CC_STAT_WIDTH, cv2.CC_STAT_HEIGHT))
        conf = float(prob_v[etq_v == i].mean())
        regiones.append(Region("vacio", round(min(max(conf, 0.0), 1.0), 3),
                               x / ancho, y / alto, min(1.0, (x + w) / ancho), min(1.0, (y + h) / alto)))
    regiones.sort(key=lambda r: -r.confianza)
    return dict(pct=round(float(pct), 2), regiones=regiones,
                estado="parcial" if parcial else "medida", mascara_vacio=vacio_ev)


def anotar(imagen_bgr: np.ndarray, mascara_vacio: np.ndarray, regiones: list[Region], calidad: int = 85) -> bytes:
    """Tiñe los vacíos y dibuja las cajas con su confianza ("vacío 0.91")."""
    salida = imagen_bgr.copy()
    if mascara_vacio.any():
        capa = salida.copy()
        capa[mascara_vacio] = COLOR_VACIO
        salida = cv2.addWeighted(capa, 0.35, salida, 0.65, 0)
    alto, ancho = salida.shape[:2]
    grosor = max(2, round(max(alto, ancho) / 400))
    escala = max(0.5, max(alto, ancho) / 1600)
    for r in regiones:
        p1 = (int(r.x_min * ancho), int(r.y_min * alto))
        p2 = (int(r.x_max * ancho) - 1, int(r.y_max * alto) - 1)
        cv2.rectangle(salida, p1, p2, COLOR_VACIO, grosor)
        texto = f"vacio {r.confianza:.2f}"
        (tw, th), base = cv2.getTextSize(texto, cv2.FONT_HERSHEY_SIMPLEX, escala, 1)
        y_txt = max(th + base + 2, p1[1])
        cv2.rectangle(salida, (p1[0], y_txt - th - base - 4), (p1[0] + tw + 8, y_txt), COLOR_VACIO, -1)
        cv2.putText(salida, texto, (p1[0] + 4, y_txt - base - 2), cv2.FONT_HERSHEY_SIMPLEX, escala, COLOR_TEXTO, 1, cv2.LINE_AA)
    ok, buf = cv2.imencode(".jpg", salida, [cv2.IMWRITE_JPEG_QUALITY, calidad])
    if not ok:
        raise RuntimeError("No se pudo codificar la imagen anotada")
    return buf.tobytes()
