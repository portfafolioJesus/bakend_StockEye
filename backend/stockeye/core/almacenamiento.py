"""Almacenamiento de fotos. Hoy: carpeta local (volumen compartido entre la
api y los workers) con la estructura recintos/R01/AAAA/MM/DD/archivo.jpg.
Para varios servidores se implementa la misma interfaz sobre S3/MinIO.
"""
from __future__ import annotations

import os
import secrets
import tempfile
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Protocol
from zoneinfo import ZoneInfo

from .config import ajustes


class Almacenamiento(Protocol):
    def guardar(self, ruta: str, datos: bytes) -> None: ...
    def leer(self, ruta: str) -> bytes: ...
    def existe(self, ruta: str) -> bool: ...
    def ruta_local(self, ruta: str) -> Path: ...


class AlmacenamientoLocal:
    def __init__(self, base: Path):
        self.base = Path(base).resolve()
        self.base.mkdir(parents=True, exist_ok=True)

    def ruta_local(self, ruta: str) -> Path:
        destino = (self.base / PurePosixPath(ruta)).resolve()
        if self.base not in destino.parents:
            raise ValueError("Ruta fuera del almacenamiento")
        return destino

    def guardar(self, ruta: str, datos: bytes) -> None:
        destino = self.ruta_local(ruta)
        destino.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix=".subida_", dir=destino.parent)
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(datos)
            os.replace(tmp, destino)       # escritura atómica: el worker nunca ve archivos a medias
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)

    def leer(self, ruta: str) -> bytes:
        return self.ruta_local(ruta).read_bytes()

    def existe(self, ruta: str) -> bool:
        try:
            return self.ruta_local(ruta).is_file()
        except ValueError:
            return False


_almacen: AlmacenamientoLocal | None = None


def almacenamiento() -> AlmacenamientoLocal:
    global _almacen
    if _almacen is None:
        _almacen = AlmacenamientoLocal(ajustes().datos_dir)
    return _almacen


def ruta_nueva(carpeta_recinto: str, prefijo: str, momento: datetime, extension: str = "jpg") -> str:
    """recintos/R01/2026/11/14/R01-CAM03_183000_a1b2.jpg (fecha y hora de Chile)."""
    local = momento.astimezone(ZoneInfo(ajustes().zona_horaria))
    seguro = "".join(c for c in prefijo if c.isalnum() or c in "-_") or "foto"
    return (f"{carpeta_recinto.strip('/')}/{local:%Y/%m/%d}/"
            f"{seguro}_{local:%H%M%S}_{secrets.token_hex(2)}.{extension}")


def ruta_anotada(ruta: str) -> str:
    base, _, _ = ruta.rpartition(".")
    return f"{base or ruta}_pred.jpg"
