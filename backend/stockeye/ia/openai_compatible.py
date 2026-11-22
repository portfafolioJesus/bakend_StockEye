"""Proveedores de visión compatibles con /chat/completions."""
from __future__ import annotations

import base64
import json
import math
import re
import time

import httpx

from ..core.config import Ajustes
from .proveedor import (PROMPT_SISTEMA, PROMPT_CLASIFICACION, ErrorIA, RespuestaIA,
                        normalizar_productos, normalizar_clasificacion, prompt_usuario, registrar)


def _espera(r: httpx.Response, predeterminada: float) -> float:
    try:
        valor = float(r.headers.get("retry-after", predeterminada))
        return min(max(valor, 1.0), 86400.0) if math.isfinite(valor) else predeterminada
    except (TypeError, ValueError):
        return predeterminada


def error_limite(r: httpx.Response, proveedor: str) -> ErrorIA:
    """Un 429 solo confirma un límite; no demuestra cuota diaria agotada."""
    try:
        cuerpo = r.json().get("error", {})
        texto = " ".join(str(cuerpo.get(k, "")) for k in ("type", "code", "message")).lower()
    except (ValueError, AttributeError, TypeError):
        texto = ""
    diario = bool(re.search(r"\b(tpd|rpd|daily|per day)\b", texto)) or any(
        t in texto for t in ("insufficient_quota", "billing_hard_limit", "daily_limit"))
    minuto = bool(re.search(r"\b(tpm|rpm|per minute)\b", texto))
    motivo = "CUOTA" if diario else "LIMITE_TEMPORAL" if minuto else "LIMITE_USO"
    descripcion = "cuota de uso agotada" if diario else "límite de uso alcanzado"
    return ErrorIA(f"{proveedor}: {descripcion}", esperar_s=_espera(r, 3600 if diario else 30),
                   codigo=429, motivo=motivo)


class ProveedorOpenAICompatible:
    def __init__(self, nombre: str, base_url: str, api_key: str | None, modelo: str, timeout_s: float = 30):
        if not api_key:
            raise ErrorIA(f"Falta configurar la API key de {nombre}", reintentable=False, motivo="CONFIGURACION")
        self.nombre, self.modelo = nombre, modelo
        self._cliente = httpx.Client(base_url=base_url.rstrip("/"), timeout=timeout_s,
                                     headers={"Authorization": f"Bearer {api_key}"})

    def _post(self, cuerpo: dict) -> dict:
        try:
            r = self._cliente.post("/chat/completions", json=cuerpo)
        except httpx.HTTPError as e:
            raise ErrorIA(f"{self.nombre}: error de red ({type(e).__name__})", motivo="RED") from e
        if r.status_code == 429:
            raise error_limite(r, self.nombre)
        if r.status_code in (401, 403):
            raise ErrorIA(f"{self.nombre}: credencial inválida o sin permiso", reintentable=False,
                          codigo=r.status_code, motivo="CONFIGURACION")
        if r.status_code == 400:
            raise ErrorIA(f"{self.nombre}: solicitud rechazada", reintentable=False, codigo=400, motivo="SOLICITUD")
        if r.status_code >= 400:
            raise ErrorIA(f"{self.nombre}: HTTP {r.status_code}", codigo=r.status_code, motivo="SERVICIO")
        try:
            return r.json()
        except ValueError as e:
            raise ErrorIA(f"{self.nombre}: respuesta ilegible", reintentable=False, motivo="RESPUESTA") from e

    def _vision(self, imagen_jpg: bytes, sistema: str, usuario: str) -> tuple[dict, dict]:
        url = "data:image/jpeg;base64," + base64.b64encode(imagen_jpg).decode()
        cuerpo = {"model": self.modelo, "temperature": 0.1, "max_completion_tokens": 400,
                  "response_format": {"type": "json_object"},
                  "messages": [{"role": "system", "content": sistema},
                               {"role": "user", "content": [{"type": "text", "text": usuario},
                                                           {"type": "image_url", "image_url": {"url": url}}]}]}
        inicio = time.perf_counter()
        datos = self._post(cuerpo)
        try:
            contenido = json.loads(datos["choices"][0]["message"]["content"])
            if not isinstance(contenido, dict):
                raise ValueError("Se requiere un objeto")
        except (KeyError, IndexError, TypeError, ValueError) as e:
            raise ErrorIA(f"{self.nombre}: respuesta no es JSON válido", reintentable=False,
                          motivo="RESPUESTA") from e
        uso = datos.get("usage") or {}
        return contenido, {"proveedor": self.nombre, "modelo": datos.get("model", self.modelo),
                           "tokens_entrada": uso.get("prompt_tokens"), "tokens_salida": uso.get("completion_tokens"),
                           "latencia_ms": int((time.perf_counter() - inicio) * 1000)}

    def analizar(self, imagen_jpg: bytes, contexto: dict) -> RespuestaIA:
        contenido, metadatos = self._vision(imagen_jpg, PROMPT_SISTEMA, prompt_usuario(contexto))
        return RespuestaIA(productos=normalizar_productos(contenido), resumen=contenido.get("resumen"),
                           crudo=contenido, **metadatos)

    def clasificar(self, imagen_jpg: bytes, categorias: list[dict]):
        catalogo = [{"codigo": c["codigo"], "nombre": c["nombre"]} for c in categorias]
        contenido, metadatos = self._vision(
            imagen_jpg, PROMPT_CLASIFICACION,
            "Catálogo de categorías permitido: " + json.dumps(catalogo, ensure_ascii=False) +
            ". Clasifica por evidencia de los productos visibles en la fotografía.")
        return normalizar_clasificacion(contenido, categorias, **metadatos)

    def probar(self) -> dict:
        inicio = time.perf_counter()
        try:
            r = self._cliente.get("/models")
        except httpx.HTTPError as e:
            return {"ok": False, "detalle": f"Error de red: {type(e).__name__}"}
        ms = int((time.perf_counter() - inicio) * 1000)
        if r.status_code in (401, 403):
            return {"ok": False, "detalle": "API key inválida", "latencia_ms": ms}
        if r.status_code >= 400:
            return {"ok": False, "detalle": f"HTTP {r.status_code}", "latencia_ms": ms}
        modelos = [m.get("id") for m in r.json().get("data", [])]
        existe = self.modelo in modelos
        return {"ok": existe, "latencia_ms": ms, "modelo": self.modelo,
                "detalle": "Conexión correcta" if existe else f"El modelo {self.modelo} no está disponible",
                "modelos_disponibles": modelos[:50]}


@registrar("groq")
def _groq(a: Ajustes, modelo: str | None):
    return ProveedorOpenAICompatible("groq", a.groq_base_url, a.groq_api_key, modelo or "qwen/qwen3.8-27b",
                                     a.ia_timeout_s)


@registrar("openai")
def _openai(a: Ajustes, modelo: str | None):
    return ProveedorOpenAICompatible("openai", a.openai_base_url, a.openai_api_key, modelo or "gpt-4.1-mini",
                                     a.ia_timeout_s)
