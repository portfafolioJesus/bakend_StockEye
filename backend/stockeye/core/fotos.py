"""Validación de fotos (común a la api y al importador de carpetas).

Acepta JPEG, PNG y WEBP; rota según el EXIF (los celulares guardan la foto
"acostada" y marcan la orientación) para que el modelo vea la góndola derecha.
"""
from __future__ import annotations

import hashlib
import io
import warnings
from dataclasses import dataclass
from datetime import datetime, timezone

from PIL import Image, ImageOps

from .almacenamiento import almacenamiento, ruta_nueva
from .config import ajustes

FORMATOS = {"JPEG": "jpg", "PNG": "png", "WEBP": "webp"}
EXTENSIONES = {".jpg", ".jpeg", ".png", ".webp"}
MAX_PIXELES = 40_000_000

# Fotos cargadas (carpeta o panel). Con punto fijo usan la fuente de carga de la
# góndola (003); solo con categoría, la del recinto (004).
SQL_IMAGEN_CARGA = """
    INSERT INTO imagen (recinto_id, gondola_id, camara_id, origen, ruta_archivo, sha256, ancho_px, alto_px, capturada_en)
    SELECT g.recinto_id, g.id, fn_fuente_carga(g.id), 'CAMARA', %s, %s, %s, %s, COALESCE(%s, now())
      FROM gondola g WHERE g.id = %s
    RETURNING id, camara_id"""

SQL_IMAGEN_CARGA_CATEGORIA = """
    INSERT INTO imagen (recinto_id, camara_id, categoria_id, origen, ruta_archivo, sha256, ancho_px, alto_px, capturada_en)
    VALUES (%s, fn_fuente_carga_recinto(%s), %s, 'CAMARA', %s, %s, %s, %s, COALESCE(%s, now()))
    RETURNING id, camara_id"""


def normalizar_texto(texto: str) -> str:
    """'Lácteos y Huevos ' → 'lacteos y huevos' (igual que fn_normalizar en la BD)."""
    import unicodedata
    sin_tildes = "".join(c for c in unicodedata.normalize("NFKD", texto) if not unicodedata.combining(c))
    return " ".join(sin_tildes.lower().split())


def slug(texto: str, largo: int = 20) -> str:
    """'Yogures y postres' → 'YOGURES-Y-POSTRES' (para códigos de punto fijo)."""
    base = "".join(c if c.isalnum() else "-" for c in normalizar_texto(texto).upper())
    return "-".join(p for p in base.split("-") if p)[:largo].strip("-")


class FotoInvalida(Exception):
    def __init__(self, mensaje: str, codigo: int = 422):
        super().__init__(mensaje)
        self.codigo = codigo


@dataclass
class Foto:
    datos: bytes
    extension: str
    ancho: int
    alto: int
    sha256: str


def normalizar(datos: bytes) -> Foto:
    limite = ajustes().max_foto_mb * 1024 * 1024
    if not datos:
        raise FotoInvalida("La foto está vacía")
    if len(datos) > limite:
        raise FotoInvalida(f"La foto supera {ajustes().max_foto_mb} MB", 413)
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(datos)) as img:
                formato = img.format
                if formato not in FORMATOS:
                    raise FotoInvalida("Formato no admitido (usa JPEG, PNG o WEBP; las fotos HEIC de iPhone hay que convertirlas)", 415)
                if img.width * img.height > MAX_PIXELES:
                    raise FotoInvalida("La foto tiene demasiados píxeles", 413)
                if img.getexif().get(0x0112, 1) != 1:
                    rotada = ImageOps.exif_transpose(img).convert("RGB")
                    salida = io.BytesIO()
                    rotada.save(salida, "JPEG", quality=92)
                    datos, formato = salida.getvalue(), "JPEG"
                    ancho, alto = rotada.size
                else:
                    ancho, alto = img.size
                    img.verify()
    except FotoInvalida:
        raise
    except Exception:
        raise FotoInvalida("El archivo no es una imagen válida")
    return Foto(datos, FORMATOS[formato], ancho, alto, hashlib.sha256(datos).hexdigest())


def guardar(foto: Foto, carpeta_recinto: str, prefijo: str, capturada_en: datetime | None) -> str:
    ruta = ruta_nueva(carpeta_recinto, prefijo, capturada_en or datetime.now(timezone.utc), foto.extension)
    almacenamiento().guardar(ruta, foto.datos)
    return ruta
