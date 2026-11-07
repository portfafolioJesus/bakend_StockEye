from __future__ import annotations

from dataclasses import asdict
import json
import os
from pathlib import Path
import re
import shutil
import tempfile

import numpy as np
from PIL import Image

from .motor import Prediccion, sha_archivo
from .registro import ahora

PATRON_ID = re.compile(r"^[0-9a-f]{32}$")


def json_seguro(valor):
    if isinstance(valor, dict): return {str(k): json_seguro(v) for k, v in valor.items()}
    if isinstance(valor, (list, tuple)): return [json_seguro(v) for v in valor]
    if isinstance(valor, np.ndarray): return json_seguro(valor.tolist())
    if isinstance(valor, np.generic): return json_seguro(valor.item())
    if isinstance(valor, float) and not np.isfinite(valor): raise ValueError("Número no finito en el resultado.")
    return valor


class Archivos:
    def __init__(self, raiz: Path):
        self.raiz = raiz.resolve()
        self.raiz.mkdir(parents=True, exist_ok=True)

    def carpeta(self, ident: str) -> Path:
        if not PATRON_ID.fullmatch(ident): raise ValueError("Identificador inválido.")
        carpeta = self.raiz / ident
        if carpeta.is_symlink() or carpeta.resolve().parent != self.raiz:
            raise ValueError("Carpeta de análisis inválida.")
        return carpeta

    def leer(self, ident: str) -> dict:
        ruta = self.carpeta(ident) / "resultado.json"
        if ruta.is_symlink(): raise ValueError("Archivo de análisis inválido.")
        def rechazar(v): raise ValueError("Número no finito en JSON.")
        documento = json.loads(ruta.read_text(encoding="utf-8"), parse_constant=rechazar)
        if not isinstance(documento, dict) or documento.get("esquema") != "stockeye-backend-1" or documento.get("analisis_id") != ident:
            raise ValueError("Resultado incompatible.")
        if documento.get("estado_proceso") != "completado" or documento.get("sucursal_id") not in (1, 2):
            raise ValueError("Resultado incompleto.")
        return documento

    def archivo(self, ident: str, tipo: str) -> Path:
        documento = self.leer(ident)
        if tipo not in {"original", "mascara", "superpuesta"}:
            raise ValueError("Tipo de archivo inválido.")
        nombre = documento["archivos"][tipo]
        if not isinstance(nombre, str) or Path(nombre).name != nombre or "\\" in nombre:
            raise ValueError("Nombre de archivo inválido.")
        carpeta = self.carpeta(ident)
        ruta = carpeta / nombre
        if ruta.is_symlink() or not ruta.is_file() or ruta.resolve().parent != carpeta.resolve():
            raise FileNotFoundError("Archivo del análisis no disponible.")
        return ruta

    def recuperar(self, trabajo: dict) -> bool:
        destino = self.carpeta(trabajo["id"])
        if not destino.exists(): return False
        d = self.leer(trabajo["id"])
        if d["sha256_original"] != trabajo["sha256"] or d["sucursal_id"] != trabajo["sucursal_id"]:
            raise ValueError("El resultado existente no corresponde a esta captura.")
        for tipo in ("original", "mascara", "superpuesta"):
            ruta = self.archivo(trabajo["id"], tipo)
            if sha_archivo(ruta) != d["sha256_archivos"][ruta.name]:
                raise ValueError("Un archivo del análisis guardado cambió.")
        return True

    def guardar(self, trabajo: dict, original: Path, prediccion: Prediccion) -> dict:
        if sha_archivo(original) != trabajo["sha256"]:
            raise ValueError("La copia de entrada cambió antes de guardar el análisis.")
        mapa, rgb = np.asarray(prediccion.mapa), np.asarray(prediccion.imagen_rgb)
        if mapa.ndim != 2 or rgb.shape != (*mapa.shape, 3) or rgb.dtype != np.uint8:
            raise ValueError("La predicción no corresponde a las dimensiones de la imagen.")
        if not set(np.unique(mapa)) <= {0, 1, 2}:
            raise ValueError("La predicción contiene clases incompatibles.")
        destino = self.carpeta(trabajo["id"])
        if destino.exists(): raise FileExistsError("Ya existe un resultado para este identificador.")
        temporal = Path(tempfile.mkdtemp(prefix=".analisis_", dir=self.raiz))
        try:
            nombre_original = "original" + original.suffix.lower()
            shutil.copyfile(original, temporal / nombre_original)
            Image.fromarray(mapa.astype(np.uint8)).save(temporal / "mascara.png")
            marcada = rgb.copy()
            vacio = mapa == 2
            marcada[vacio] = np.clip(.45 * rgb[vacio] + .55 * np.array([250, 204, 0]), 0, 255).astype(np.uint8)
            Image.fromarray(marcada).save(temporal / "superpuesta.jpg", quality=92)
            archivos = {"original": nombre_original, "mascara": "mascara.png", "superpuesta": "superpuesta.jpg"}
            documento = dict(esquema="stockeye-backend-1", analisis_id=trabajo["id"], captura_id=trabajo["id"],
                foto=trabajo["nombre"], sucursal_id=trabajo["sucursal_id"], sucursal=f"Sucursal {trabajo['sucursal_id']}",
                sha256_original=trabajo["sha256"], fecha_analisis=ahora(), estado_proceso="completado",
                estado_medicion=prediccion.estado_medicion, version_modelo=prediccion.version_modelo,
                modelo_sha256=prediccion.modelo_sha256, pipeline="stockeye-v6-corregido-1",
                segundos=prediccion.segundos, operacion=prediccion.operacion, recursos=prediccion.recursos,
                dimensiones={"ancho": mapa.shape[1], "alto": mapa.shape[0]},
                coordenadas="pixeles_de_imagen_original_decodificada_con_orientacion_exif",
                cantidad_gondolas_detectadas=len(prediccion.gondolas),
                cantidad_regiones_vacias=sum(g["cantidad_regiones_vacias"] for g in prediccion.gondolas),
                gondolas=prediccion.gondolas, archivos=archivos,
                sha256_archivos={nombre: sha_archivo(temporal / nombre) for nombre in archivos.values()})
            documento = json_seguro(documento)
            with (temporal / "resultado.json").open("w", encoding="utf-8") as f:
                json.dump(documento, f, ensure_ascii=False, indent=2, allow_nan=False)
                f.flush(); os.fsync(f.fileno())
            temporal.rename(destino)
            return documento
        finally:
            if temporal.exists(): shutil.rmtree(temporal)
