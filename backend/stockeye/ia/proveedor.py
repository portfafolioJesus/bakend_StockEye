"""Interfaz para la IA que identifica el producto faltante.

Cambiar de proveedor = escribir una clase que cumpla `ProveedorIA`,
registrarla en PROVEEDORES y cambiar IA_PROVEEDOR (o el selector del panel).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Protocol

from ..core.config import Ajustes


class ErrorIA(Exception):
    def __init__(self, mensaje: str, reintentable: bool = True, esperar_s: float | None = None):
        super().__init__(mensaje)
        self.reintentable = reintentable
        self.esperar_s = esperar_s


@dataclass
class RespuestaIA:
    proveedor: str
    modelo: str
    productos: list[dict]               # [{"producto": "...", "categoria": "...", "confianza": 0.86}]
    resumen: str | None = None
    tokens_entrada: int | None = None
    tokens_salida: int | None = None
    latencia_ms: int | None = None
    crudo: dict = field(default_factory=dict)


class ProveedorIA(Protocol):
    nombre: str
    modelo: str

    def analizar(self, imagen_jpg: bytes, contexto: dict) -> RespuestaIA: ...

    def probar(self) -> dict: ...


PROMPT_SISTEMA = (
    "Eres un asistente de reposición de un supermercado en Chile. Recibes la foto de una góndola; "
    "las zonas vacías están marcadas con recuadros naranjos. Identifica qué productos faltan en esos "
    "espacios usando los productos vecinos, los carteles de precio y la categoría de la góndola. "
    "Responde SOLO con JSON válido con esta forma: "
    '{"productos_faltantes": [{"producto": "nombre comercial y formato, p. ej. Arroz grado 1, 1 kg", '
    '"categoria": "categoría", "confianza": 0.0}], "resumen": "una frase"}. '
    "Máximo 3 productos, ordenados por confianza (0 a 1). Si no puedes saberlo, devuelve la lista vacía."
)


def prompt_usuario(contexto: dict) -> str:
    partes = [f"Góndola {contexto.get('gondola') or 'sin código'}"]
    if contexto.get("categoria"):
        partes.append(f"categoría {contexto['categoria']}")
    if contexto.get("porcentaje_vacio") is not None:
        partes.append(f"el modelo de visión estimó {contexto['porcentaje_vacio']} % de vacío")
    return ", ".join(partes) + ". ¿Qué producto falta?"


def normalizar_productos(datos: dict) -> list[dict]:
    salida = []
    for p in (datos.get("productos_faltantes") or datos.get("productos") or [])[:3]:
        if not isinstance(p, dict) or not str(p.get("producto", "")).strip():
            continue
        try:
            conf = min(max(float(p.get("confianza", 0)), 0.0), 1.0)
        except (TypeError, ValueError):
            conf = 0.0
        salida.append({"producto": str(p["producto"]).strip()[:150],
                       "categoria": (str(p.get("categoria")).strip()[:80] if p.get("categoria") else None),
                       "confianza": round(conf, 3)})
    return sorted(salida, key=lambda p: -p["confianza"])


PROVEEDORES: dict[str, Callable[[Ajustes, str | None], ProveedorIA]] = {}


def registrar(nombre: str):
    def deco(fabrica):
        PROVEEDORES[nombre] = fabrica
        return fabrica
    return deco


def crear_proveedor(nombre: str, modelo: str | None, a: Ajustes) -> ProveedorIA:
    from . import openai_compatible  # noqa: F401  (registra groq y openai)
    if nombre not in PROVEEDORES:
        raise ErrorIA(f"Proveedor de IA desconocido: {nombre}. Disponibles: {', '.join(sorted(PROVEEDORES))}",
                      reintentable=False)
    return PROVEEDORES[nombre](a, a.ia_modelo or modelo)
