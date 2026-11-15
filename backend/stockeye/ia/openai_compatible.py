"""Proveedores con API compatible con OpenAI (/chat/completions): Groq y OpenAI.

Groq: https://console.groq.com/docs/vision — imagen en base64 (data URL),
salida en modo JSON. El modelo se configura en el panel o con IA_MODELO.
"""
from __future__ import annotations

import base64
import json
import time

import httpx

from ..core.config import Ajustes
from .proveedor import PROMPT_SISTEMA, ErrorIA, RespuestaIA, normalizar_productos, prompt_usuario, registrar


class ProveedorOpenAICompatible:
    def __init__(self, nombre: str, base_url: str, api_key: str | None, modelo: str, timeout_s: float = 30):
        if not api_key:
            raise ErrorIA(f"Falta la API key de {nombre} (variable de entorno)", reintentable=False)
        self.nombre, self.modelo = nombre, modelo
        self._cliente = httpx.Client(base_url=base_url.rstrip("/"), timeout=timeout_s,
                                     headers={"Authorization": f"Bearer {api_key}"})

    def _post(self, cuerpo: dict) -> dict:
        try:
            r = self._cliente.post("/chat/completions", json=cuerpo)
        except httpx.HTTPError as e:
            raise ErrorIA(f"{self.nombre}: error de red ({type(e).__name__})") from e
        if r.status_code == 429:
            espera = float(r.headers.get("retry-after", "20") or 20)
            raise ErrorIA(f"{self.nombre}: límite de uso alcanzado", esperar_s=espera)
        if r.status_code in (401, 403):
            raise ErrorIA(f"{self.nombre}: API key inválida o sin permiso", reintentable=False)
        if r.status_code == 400:
            raise ErrorIA(f"{self.nombre}: solicitud rechazada: {r.text[:300]}", reintentable=False)
        if r.status_code >= 400:
            raise ErrorIA(f"{self.nombre}: HTTP {r.status_code}")
        return r.json()

    def analizar(self, imagen_jpg: bytes, contexto: dict) -> RespuestaIA:
        url = "data:image/jpeg;base64," + base64.b64encode(imagen_jpg).decode()
        cuerpo = {
            "model": self.modelo,
            "temperature": 0.1,
            "max_completion_tokens": 400,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": PROMPT_SISTEMA},
                {"role": "user", "content": [
                    {"type": "text", "text": prompt_usuario(contexto)},
                    {"type": "image_url", "image_url": {"url": url}},
                ]},
            ],
        }
        inicio = time.perf_counter()
        datos = self._post(cuerpo)
        latencia = int((time.perf_counter() - inicio) * 1000)
        try:
            texto = datos["choices"][0]["message"]["content"]
            contenido = json.loads(texto)
        except (KeyError, IndexError, TypeError, json.JSONDecodeError) as e:
            raise ErrorIA(f"{self.nombre}: respuesta no es JSON válido", reintentable=False) from e
        uso = datos.get("usage") or {}
        return RespuestaIA(proveedor=self.nombre, modelo=datos.get("model", self.modelo),
                           productos=normalizar_productos(contenido),
                           resumen=(contenido.get("resumen") or None),
                           tokens_entrada=uso.get("prompt_tokens"), tokens_salida=uso.get("completion_tokens"),
                           latencia_ms=latencia, crudo=contenido)

    def probar(self) -> dict:
        """Verifica la API key y que el modelo exista, sin gastar tokens."""
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
