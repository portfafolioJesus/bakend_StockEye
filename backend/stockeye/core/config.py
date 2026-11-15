"""Configuración por variables de entorno (o archivo .env). Ver .env.example."""
from __future__ import annotations

import os
import socket
from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

RAIZ_BACKEND = Path(__file__).resolve().parents[2]


def _db_por_defecto() -> Path:
    # En Docker los SQL se copian a /app/db; en desarrollo están en ../db
    for candidato in (RAIZ_BACKEND / "db", RAIZ_BACKEND.parent / "db"):
        if candidato.is_dir():
            return candidato
    return RAIZ_BACKEND.parent / "db"


class Ajustes(BaseSettings):
    model_config = SettingsConfigDict(env_file=(".env", "../.env"), extra="ignore")

    entorno: str = "desarrollo"                       # desarrollo | produccion
    database_url: str = "postgresql://stockeye:stockeye@localhost:5433/stockeye"
    db_pool_min: int = 1
    db_pool_max: int = 8
    auto_migrar: bool = True                          # la api aplica migraciones al iniciar
    db_dir: Path = _db_por_defecto()

    jwt_secreto: str = "desarrollo-cambia-este-secreto-por-uno-largo-y-aleatorio"
    jwt_minutos_acceso: int = 12 * 60
    jwt_dias_refresco: int = 30
    url_firma_minutos: int = 120                      # validez de los links firmados a fotos

    datos_dir: Path = RAIZ_BACKEND / "datos"          # aquí viven recintos/R01/AAAA/MM/DD/...
    modelos_dir: Path = RAIZ_BACKEND / "modelos"
    max_foto_mb: int = 15
    entradas_dir: Path = RAIZ_BACKEND.parent / "entradas"   # carpeta vigilada por el importador
    importador_intervalo_s: float = 5.0
    cors_origenes: str = "http://localhost:5173,http://localhost:8080"
    zona_horaria: str = "America/Santiago"

    # Worker de inferencia
    worker_recintos: str = "*"                        # "*" o "R01,R02" (workers dedicados)
    worker_nombre: str = f"{socket.gethostname()}-{os.getpid()}"
    ort_hilos: int | None = None                      # por defecto: los del manifiesto del modelo
    inferencia_dispositivo: str = "cpu"               # cpu | cuda
    inferencia_presupuesto_s: float = 3.0
    vram_max_gb: float = 2.5
    lease_minutos: int = 5

    # Push
    fcm_credenciales: Path | None = None              # JSON de la cuenta de servicio de Firebase
    vapid_publica: str | None = None
    vapid_privada: str | None = None
    vapid_contacto: str = "mailto:soporte@stockeye.local"

    # IA de producto (intercambiable)
    ia_proveedor: str = "groq"
    ia_modelo: str | None = None                      # si se define, pisa el de la BD
    ia_timeout_s: float = 30.0
    groq_api_key: str | None = None
    groq_base_url: str = "https://api.groq.com/openai/v1"
    openai_api_key: str | None = None
    openai_base_url: str = "https://api.openai.com/v1"

    @field_validator("ort_hilos", "fcm_credenciales", "vapid_publica", "vapid_privada", "ia_modelo",
                     "groq_api_key", "openai_api_key", mode="before")
    @classmethod
    def _vacio_a_none(cls, v):
        return None if v in ("", None) else v

    @property
    def lista_cors(self) -> list[str]:
        return [o.strip() for o in self.cors_origenes.split(",") if o.strip()]

    @property
    def es_produccion(self) -> bool:
        return self.entorno.lower().startswith("prod")

    def validar_produccion(self) -> None:
        if self.es_produccion and (self.jwt_secreto.startswith("desarrollo") or len(self.jwt_secreto) < 32):
            raise RuntimeError("JWT_SECRETO debe ser un valor aleatorio de al menos 32 caracteres en producción")


@lru_cache
def ajustes() -> Ajustes:
    return Ajustes()
