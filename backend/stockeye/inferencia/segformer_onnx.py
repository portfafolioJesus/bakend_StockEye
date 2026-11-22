"""SegFormer exportado a ONNX e inferido con onnxruntime.

No usa PyTorch: el worker ocupa ~0,4 GB de RAM y entra en el límite de 4 GB.
Solo modo "completa" (una pasada): tta/mosaicos multiplican el tiempo y no
caben en el presupuesto de 3 s por foto en CPU.
"""
from __future__ import annotations

import logging
import math
import os
import time
from pathlib import Path

import cv2
import numpy as np

from .motor import Resultado, recortar_roi
from .postproceso import Parametros, analizar, anotar, softmax_canales

log = logging.getLogger(__name__)

MEDIA = np.array([0.485, 0.456, 0.406], np.float32)
DESV = np.array([0.229, 0.224, 0.225], np.float32)


def tamano_trabajo(alto: int, ancho: int, lado: int, pixeles_max: int) -> tuple[int, int]:
    """Lado mayor ≤ `lado` y área ≤ `pixeles_max`, en múltiplos de 32.

    El tope de píxeles hace que el tiempo no dependa de la proporción de la foto
    (una foto 4:3 del celular tendría 33 % más píxeles que una 16:9 de cámara).
    """
    escala = min(lado / max(alto, ancho), math.sqrt(pixeles_max / (alto * ancho)))
    return max(32, round(alto * escala / 32) * 32), max(32, round(ancho * escala / 32) * 32)


def decodificar(datos: bytes, lado: int) -> np.ndarray:
    """Decodifica el JPEG ya reducido (escalado DCT) si es mucho más grande que lo que usa la red."""
    arreglo = np.frombuffer(datos, np.uint8)
    img = None
    if len(datos) > 1_500_000:   # fotos de celular de 8-12 MP
        img = cv2.imdecode(arreglo, cv2.IMREAD_REDUCED_COLOR_2)
        if img is not None and min(img.shape[:2]) < lado * 0.6:
            img = None
    if img is None:
        img = cv2.imdecode(arreglo, cv2.IMREAD_COLOR)
    if img is None or img.ndim != 3:
        raise ValueError("No se pudo decodificar la imagen")
    return img


def crear_sesion(ruta: Path, hilos: int, dispositivo: str = "cpu", vram_max_gb: float = 2.5):
    import onnxruntime as ort

    opciones = ort.SessionOptions()
    opciones.intra_op_num_threads = max(1, hilos)
    opciones.inter_op_num_threads = 1
    opciones.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
    opciones.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
    # Con entradas de tamaño variable el patrón de memoria no acelera y suma ~200 MB de RAM.
    opciones.enable_mem_pattern = False
    proveedores: list = ["CPUExecutionProvider"]
    if dispositivo == "cuda":
        if "CUDAExecutionProvider" not in ort.get_available_providers():
            raise RuntimeError("INFERENCIA_DISPOSITIVO=cuda pero onnxruntime-gpu/CUDA no está disponible")
        proveedores = [("CUDAExecutionProvider", {
            "gpu_mem_limit": int(vram_max_gb * 1024 ** 3),      # tope de VRAM (el equipo tiene 3 GB)
            "arena_extend_strategy": "kSameAsRequested",
        }), "CPUExecutionProvider"]
    return ort.InferenceSession(str(ruta), sess_options=opciones, providers=proveedores)


class MotorSegFormerOnnx:
    familia = "SEGFORMER"

    def __init__(self, ruta_onnx: str | Path, *, lado: int = 1280, pixeles_max: int = 600_000,
                 umbral_vacio: float = 0.5, parametros: dict | None = None, hilos: int | None = None,
                 dispositivo: str = "cpu"):
        self.ruta = Path(ruta_onnx)
        if not self.ruta.is_file():
            raise FileNotFoundError(f"No existe el modelo ONNX {self.ruta}. Ejecuta herramientas/empaquetar_modelo.py")
        self.lado = int(lado)
        self.pixeles_max = int(pixeles_max)
        self.parametros = Parametros.desde_dict(parametros, umbral_vacio)
        self.hilos = hilos or max(1, (os.cpu_count() or 2) // 2)
        self.sesion = crear_sesion(self.ruta, self.hilos, dispositivo)
        self.entrada = self.sesion.get_inputs()[0].name
        self.descripcion = f"segformer-onnx lado={self.lado} px={self.pixeles_max} umbral={self.parametros.umbral_vacio} hilos={self.hilos}"
        # Calentamiento: la primera corrida reserva memoria y no debe contar en las métricas.
        self.inferir(np.full((720, 1280, 3), 127, np.uint8))
        log.info("Modelo cargado: %s (%s)", self.ruta.name, self.descripcion)

    def probabilidades(self, imagen_bgr: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        alto, ancho = tamano_trabajo(*imagen_bgr.shape[:2], self.lado, self.pixeles_max)
        redim = cv2.resize(imagen_bgr, (ancho, alto), interpolation=cv2.INTER_AREA
                           if imagen_bgr.shape[0] > alto else cv2.INTER_LINEAR)
        rgb = redim[..., ::-1].astype(np.float32) * (1 / 255.0)
        x = ((rgb - MEDIA) / DESV).transpose(2, 0, 1)[None].copy()
        logits = self.sesion.run(None, {self.entrada: x})[0][0]          # (3, alto/4, ancho/4)
        logits = cv2.resize(logits.transpose(1, 2, 0), (ancho, alto), interpolation=cv2.INTER_LINEAR)
        return softmax_canales(logits), redim

    def inferir_bytes(self, datos: bytes, roi: list | None = None, tamano_original: tuple[int, int] | None = None) -> Resultado:
        inicio = time.perf_counter()
        resultado = self.inferir(decodificar(datos, self.lado), roi)
        if tamano_original:
            resultado.ancho_px, resultado.alto_px = tamano_original
        resultado.ms_inferencia = int((time.perf_counter() - inicio) * 1000)
        return resultado

    def inferir(self, imagen_bgr: np.ndarray, roi: list | None = None) -> Resultado:
        inicio = time.perf_counter()
        alto0, ancho0 = imagen_bgr.shape[:2]
        imagen = recortar_roi(imagen_bgr, roi)
        prob, redim = self.probabilidades(imagen)
        analisis = analizar(prob, redim, self.parametros)
        anotada = anotar(redim, analisis["mascara_vacio"], analisis["regiones"])
        ms = int((time.perf_counter() - inicio) * 1000)
        return Resultado(
            porcentaje_vacio=analisis["pct"],
            regiones=analisis["regiones"],
            num_vacios=len(analisis["regiones"]),
            num_productos=0,   # SegFormer segmenta áreas; no cuenta productos individuales
            anotada_jpg=anotada,
            ancho_px=ancho0,
            alto_px=alto0,
            ms_inferencia=ms,
            estado_medicion=analisis["estado"],
            detalle={"lado": self.lado, "pixeles_max": self.pixeles_max, "resolucion_trabajo": list(redim.shape[:2][::-1]),
                     "umbral_vacio": self.parametros.umbral_vacio},
        )
