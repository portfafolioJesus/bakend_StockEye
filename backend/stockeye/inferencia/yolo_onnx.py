"""YOLO (Ultralytics v8/11, exportado con `yolo export format=onnx`) con onnxruntime.

Alternativa intercambiable a SegFormer (familia YOLO en modelo_ia). Fórmula
de PLAN.md §8: % vacío = área(∪ cajas "vacio") / área(∪ cajas "vacio" ∪ "producto").
"""
from __future__ import annotations

import time
from pathlib import Path

import cv2
import numpy as np

from .motor import Region, Resultado, recortar_roi
from .postproceso import COLOR_VACIO
from .segformer_onnx import crear_sesion, decodificar


class MotorYoloOnnx:
    familia = "YOLO"

    def __init__(self, ruta_onnx: str | Path, *, clases: dict, umbral_confianza: float = 0.25,
                 imgsz: int = 640, iou_nms: float = 0.5, hilos: int = 2, dispositivo: str = "cpu"):
        self.ruta = Path(ruta_onnx)
        self.sesion = crear_sesion(self.ruta, hilos, dispositivo)
        self.entrada = self.sesion.get_inputs()[0].name
        self.clases = {int(k): v for k, v in clases.items()}
        self.conf, self.iou, self.imgsz = float(umbral_confianza), float(iou_nms), int(imgsz)
        self.lado = self.imgsz
        self.descripcion = f"yolo-onnx imgsz={imgsz} conf={self.conf}"

    def _letterbox(self, img):
        h, w = img.shape[:2]
        r = self.imgsz / max(h, w)
        nh, nw = round(h * r), round(w * r)
        lienzo = np.full((self.imgsz, self.imgsz, 3), 114, np.uint8)
        y0, x0 = (self.imgsz - nh) // 2, (self.imgsz - nw) // 2
        lienzo[y0:y0 + nh, x0:x0 + nw] = cv2.resize(img, (nw, nh))
        return lienzo, r, x0, y0

    def inferir_bytes(self, datos: bytes, roi=None, tamano_original=None) -> Resultado:
        inicio = time.perf_counter()
        r = self.inferir(decodificar(datos, self.imgsz), roi)
        if tamano_original:
            r.ancho_px, r.alto_px = tamano_original
        r.ms_inferencia = int((time.perf_counter() - inicio) * 1000)
        return r

    def inferir(self, imagen_bgr: np.ndarray, roi=None) -> Resultado:
        inicio = time.perf_counter()
        alto0, ancho0 = imagen_bgr.shape[:2]
        img = recortar_roi(imagen_bgr, roi)
        h, w = img.shape[:2]
        lienzo, r, x0, y0 = self._letterbox(img)
        x = (lienzo[..., ::-1].astype(np.float32) / 255.0).transpose(2, 0, 1)[None].copy()
        salida = self.sesion.run(None, {self.entrada: x})[0][0]          # (4 + nc, N)
        pred = salida.T
        puntajes = pred[:, 4:]
        cls = puntajes.argmax(1)
        conf = puntajes.max(1)
        keep = conf >= self.conf
        pred, cls, conf = pred[keep], cls[keep], conf[keep]
        cajas = []
        if len(pred):
            cx, cy, bw, bh = pred[:, 0], pred[:, 1], pred[:, 2], pred[:, 3]
            x1 = ((cx - bw / 2) - x0) / r; y1 = ((cy - bh / 2) - y0) / r
            x2 = ((cx + bw / 2) - x0) / r; y2 = ((cy + bh / 2) - y0) / r
            rects = [[float(a), float(b), float(c - a), float(d - b)] for a, b, c, d in zip(x1, y1, x2, y2)]
            idx = cv2.dnn.NMSBoxesBatched(rects, conf.tolist(), cls.tolist(), self.conf, self.iou)
            for i in np.array(idx).flatten():
                a, b = max(0.0, x1[i]), max(0.0, y1[i])
                c, d = min(float(w), x2[i]), min(float(h), y2[i])
                if c - a > 1 and d - b > 1:
                    cajas.append((self.clases.get(int(cls[i]), str(cls[i])), float(conf[i]), a, b, c, d))
        vacio = np.zeros((h, w), bool)
        producto = np.zeros((h, w), bool)
        for nombre, _, a, b, c, d in cajas:
            (vacio if nombre == "vacio" else producto)[int(b):int(d), int(a):int(c)] = True
        a_vacio = int(vacio.sum())
        a_total = a_vacio + int((producto & ~vacio).sum())
        pct = round(100 * a_vacio / a_total, 2) if a_total else 0.0
        regiones = [Region(n, round(c, 3), a / w, b / h, min(1.0, cc / w), min(1.0, d / h))
                    for n, c, a, b, cc, d in cajas]
        anotada = img.copy()
        for n, c, a, b, cc, d in cajas:
            color = COLOR_VACIO if n == "vacio" else (120, 170, 60)
            cv2.rectangle(anotada, (int(a), int(b)), (int(cc), int(d)), color, 2)
            if n == "vacio":
                cv2.putText(anotada, f"vacio {c:.2f}", (int(a) + 3, max(12, int(b) - 4)),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1, cv2.LINE_AA)
        _, buf = cv2.imencode(".jpg", anotada, [cv2.IMWRITE_JPEG_QUALITY, 85])
        return Resultado(porcentaje_vacio=pct, regiones=[x for x in regiones if x.clase == "vacio"],
                         num_vacios=sum(1 for x in regiones if x.clase == "vacio"),
                         num_productos=sum(1 for x in regiones if x.clase != "vacio"),
                         anotada_jpg=buf.tobytes(), ancho_px=ancho0, alto_px=alto0,
                         ms_inferencia=int((time.perf_counter() - inicio) * 1000),
                         estado_medicion="medida" if a_total else "sin_gondola",
                         detalle={"imgsz": self.imgsz, "cajas": len(cajas)})
