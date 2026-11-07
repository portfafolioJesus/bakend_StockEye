"""Carga local de SegFormer. No descarga modelos ni ejecuta entrenamiento."""
from __future__ import annotations

from dataclasses import dataclass, fields
import hashlib
import json
import math
from pathlib import Path
import time
import warnings

import numpy as np
from PIL import Image

from .configuracion import Configuracion

CLASES = {"0": "fondo", "1": "ocupado", "2": "vacio"}
FORMATO = "stockeye-local-1"
PIPELINE = "stockeye-v6-corregido-1"


def sha_archivo(ruta: Path) -> str:
    h = hashlib.sha256()
    with Path(ruta).open("rb") as f:
        for bloque in iter(lambda: f.read(1024 * 1024), b""):
            h.update(bloque)
    return h.hexdigest()


@dataclass
class Prediccion:
    imagen_rgb: np.ndarray
    mapa: np.ndarray
    gondolas: list[dict]
    estado_medicion: str
    segundos: float
    version_modelo: str
    modelo_sha256: str
    operacion: dict
    recursos: dict


def validar_imagen(ruta: Path, cfg: Configuracion):
    if ruta.stat().st_size > cfg.limites.max_archivo_mb * 1024**2:
        raise ValueError("La imagen supera max_archivo_mb.")
    with warnings.catch_warnings():
        warnings.simplefilter("error", Image.DecompressionBombWarning)
        with Image.open(ruta) as img:
            if img.width * img.height > cfg.limites.max_pixeles:
                raise ValueError("La imagen supera max_pixeles.")
            if img.format not in {"JPEG", "PNG", "WEBP", "BMP", "TIFF"}:
                raise ValueError("Formato de imagen no admitido.")
            if getattr(img, "n_frames", 1) != 1:
                raise ValueError("Utiliza imágenes estáticas de un solo fotograma.")
            img.verify()


class MotorSegFormer:
    def __init__(self, configuracion: Configuracion):
        self.configuracion = configuracion
        ruta = configuracion.modelo.archivo
        if not ruta.is_file():
            raise FileNotFoundError("Falta modelos/modelo.pt. Copia el modelo de tu compañero y reinicia el backend.")
        import torch
        from . import inferencia_base as base
        self.torch, self.base = torch, base
        torch.set_num_threads(configuracion.limites.hilos_cpu)
        self.sha256 = sha_archivo(ruta)
        checkpoint = torch.load(ruta, map_location="cpu", weights_only=True)
        if not isinstance(checkpoint, dict) or not isinstance(checkpoint.get("modelo"), dict):
            raise ValueError("El .pt debe contener 'modelo' con el state_dict de SegFormer StockEye.")
        if checkpoint.get("formato") not in (None, FORMATO):
            raise ValueError("Formato de .pt no compatible.")
        if checkpoint.get("pipeline") != PIPELINE:
            raise ValueError("Falta el pipeline compatible. Usa preparar_modelo.py con el checkpoint de StockEye v6.")
        if checkpoint.get("clases", CLASES) != CLASES:
            raise ValueError("Las clases deben ser 0=fondo, 1=ocupado y 2=vacio.")
        arquitectura = checkpoint.get("model_config")
        if arquitectura is None and configuracion.modelo.arquitectura_json:
            arquitectura = json.loads(configuracion.modelo.arquitectura_json.read_text(encoding="utf-8"))
        if not isinstance(arquitectura, dict):
            raise ValueError("Falta model_config en el .pt. Empaqueta el modelo con preparar_modelo.py; no se descargará arquitectura de Internet.")
        operacion = checkpoint.get("operacion", {})
        modo = configuracion.modelo.modo or operacion.get("modo")
        umbral = configuracion.modelo.umbral_vacio
        if umbral is None:
            umbral = operacion.get("umbral_vacio")
        if modo not in {"completa", "tta", "mosaicos", "mosaicos+tta"}:
            raise ValueError("Falta el modo validado. Inclúyelo en el .pt con preparar_modelo.py o configura modelo.modo.")
        if isinstance(umbral, bool) or not isinstance(umbral, (int, float)) or not math.isfinite(umbral) or not 0 < umbral < 1:
            raise ValueError("Falta umbral_vacio válido. Inclúyelo en el .pt o configúralo explícitamente.")
        campos = {f.name for f in fields(base.Config)}
        valores = checkpoint.get("config", {})
        if not isinstance(valores, dict):
            raise ValueError("La configuración del .pt no es un objeto.")
        valores = {k: v for k, v in valores.items() if k in campos}
        limites = configuracion.limites
        valores.update(tiempo_max_s=limites.tiempo_max_s, max_ram_gb=limites.max_ram_gb,
                       max_vram_inferencia_gb=limites.max_vram_gb, max_pixeles_imagen=limites.max_pixeles)
        self.cfg = base.validar_config(base.Config(**valores))
        seleccion = configuracion.modelo.dispositivo
        if seleccion == "cuda" and not torch.cuda.is_available():
            raise ValueError("Se configuró CUDA pero PyTorch no detecta una GPU compatible. Usa cpu o auto.")
        self.dispositivo = "cuda" if seleccion == "cuda" or seleccion == "auto" and torch.cuda.is_available() else "cpu"
        arquitectura = base.SegformerConfig.from_dict(arquitectura)
        if arquitectura.num_labels != 3 or arquitectura.num_channels != 3:
            raise ValueError("El modelo debe tener tres clases y recibir imágenes RGB.")
        modelo = base.SegformerForSemanticSegmentation(arquitectura)
        modelo.load_state_dict(checkpoint["modelo"], strict=True)
        del checkpoint
        self.segmentador = base.SegmentadorSegFormer(modelo.to(self.dispositivo).eval(), self.cfg, modo, float(umbral))
        if sha_archivo(ruta) != self.sha256:
            raise ValueError("El .pt cambió durante la carga. Detén el servicio antes de reemplazarlo.")
        self.version = f"pt-{self.sha256[:12]}"
        self.operacion = {"modo": modo, "umbral_vacio": float(umbral)}
        base.comprobar_recursos(self.cfg)

    def inferir(self, ruta: Path) -> Prediccion:
        import cv2
        validar_imagen(ruta, self.configuracion)
        base, torch, seg = self.base, self.torch, self.segmentador
        base.comprobar_recursos(self.cfg)
        if self.dispositivo == "cuda":
            torch.cuda.reset_peak_memory_stats()
        base.sincronizar_cuda(seg.modelo)
        inicio = time.perf_counter()
        # imdecode admite rutas Windows con caracteres Unicode al leer mediante Python.
        img = cv2.imdecode(np.fromfile(ruta, dtype=np.uint8), cv2.IMREAD_COLOR)
        if img is None or img.ndim != 3:
            raise ValueError("No se pudo decodificar la fotografía.")
        if img.shape[0] * img.shape[1] > self.cfg.max_pixeles_imagen:
            raise ValueError("La imagen decodificada supera max_pixeles.")
        with torch.inference_mode():
            probabilidades = seg.prob(img)
        mapa = base.mapa_desde_prob(probabilidades, seg.umbral)
        gondolas = base.postprocesar_mapa(img, mapa, self.cfg)
        base.sincronizar_cuda(seg.modelo)
        segundos = time.perf_counter() - inicio
        recursos = base.comprobar_recursos(self.cfg)
        if segundos > self.cfg.tiempo_max_s:
            raise TimeoutError(f"La inferencia tardó {segundos:.2f}s y supera tiempo_max_s={self.cfg.tiempo_max_s}.")
        estado = "sin_gondola" if not gondolas else "parcial" if any(g["estado"] == "parcial" for g in gondolas) else "medida"
        return Prediccion(img[..., ::-1].copy(), mapa, gondolas, estado, round(segundos, 4),
                          self.version, self.sha256, self.operacion, recursos)
