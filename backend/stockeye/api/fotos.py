"""Lectura de fotos subidas por HTTP (cámaras, celulares y panel)."""
from __future__ import annotations

from datetime import datetime

from fastapi import HTTPException, UploadFile

from ..core.config import ajustes
from ..core.fotos import Foto, FotoInvalida, guardar, normalizar


async def leer_foto(archivo: UploadFile) -> Foto:
    datos = await archivo.read(ajustes().max_foto_mb * 1024 * 1024 + 1)
    try:
        return normalizar(datos)
    except FotoInvalida as e:
        raise HTTPException(e.codigo, str(e))


def guardar_foto(foto: Foto, carpeta_recinto: str, prefijo: str, capturada_en: datetime | None) -> str:
    return guardar(foto, carpeta_recinto, prefijo, capturada_en)
