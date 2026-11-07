from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Modelo(BaseModel):
    model_config = ConfigDict(extra="forbid")
    archivo: Path = Path("modelos/modelo.pt")
    arquitectura_json: Path | None = None
    modo: Literal["completa", "tta", "mosaicos", "mosaicos+tta"] | None = None
    umbral_vacio: float | None = Field(default=None, gt=0, lt=1)
    dispositivo: Literal["auto", "cpu", "cuda"] = "auto"


class Limites(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    max_archivo_mb: float = Field(default=20, gt=0)
    max_pixeles: int = Field(default=20_000_000, gt=0)
    max_ram_gb: float | None = Field(default=4, gt=0)
    max_vram_gb: float | None = Field(default=2, gt=0)
    tiempo_max_s: float = Field(default=120, gt=0)
    hilos_cpu: int = Field(default=2, ge=1, le=128)


class API(BaseModel):
    model_config = ConfigDict(extra="forbid")
    host: str = "127.0.0.1"
    puerto: int = Field(default=8000, ge=1, le=65535)


class Configuracion(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    carpetas: dict[int, Path]
    datos: Path = Path("datos")
    modelo: Modelo = Field(default_factory=Modelo)
    limites: Limites = Field(default_factory=Limites)
    revision_segundos: float = Field(default=30, ge=1)
    estabilidad_segundos: float = Field(default=2, ge=0)
    api: API = Field(default_factory=API)

    @model_validator(mode="after")
    def validar_carpetas(self):
        if set(self.carpetas) != {1, 2}:
            raise ValueError("Configura exactamente las sucursales 1 y 2.")
        raices = [p.resolve() for p in self.carpetas.values()]
        datos = self.datos.resolve()
        for i, raiz in enumerate(raices):
            for otra in raices[i + 1:]:
                if raiz == otra or raiz in otra.parents or otra in raiz.parents:
                    raise ValueError("Las carpetas de sucursales deben ser distintas y no contenerse.")
            if datos == raiz or raiz in datos.parents or datos in raiz.parents:
                raise ValueError("La carpeta de datos debe estar separada de las entradas.")
            modelo = self.modelo.archivo.resolve()
            if modelo == raiz or raiz in modelo.parents:
                raise ValueError("El modelo debe estar fuera de las entradas.")
        return self

    @property
    def resultados(self) -> Path:
        return self.datos / "resultados"

    @property
    def temporales(self) -> Path:
        return self.datos / "pendientes"

    def crear_carpetas(self):
        for ruta in [*self.carpetas.values(), self.datos, self.resultados,
                     self.temporales, self.modelo.archivo.parent]:
            ruta.mkdir(parents=True, exist_ok=True)


def cargar_configuracion(archivo: str | Path = "config.json") -> Configuracion:
    archivo = Path(archivo).resolve()
    contenido = json.loads(archivo.read_text(encoding="utf-8"))
    base = archivo.parent
    def resolver(valor):
        ruta = Path(valor).expanduser()
        return str((base / ruta).resolve()) if not ruta.is_absolute() else str(ruta.resolve())
    contenido["carpetas"] = {k: resolver(v) for k, v in contenido["carpetas"].items()}
    contenido["datos"] = resolver(contenido.get("datos", "datos"))
    modelo = contenido.setdefault("modelo", {})
    modelo["archivo"] = resolver(modelo.get("archivo", "modelos/modelo.pt"))
    if modelo.get("arquitectura_json"):
        modelo["arquitectura_json"] = resolver(modelo["arquitectura_json"])
    return Configuracion.model_validate(contenido)
