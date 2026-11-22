"""Registro de destinos push: tokens FCM (app Android) y suscripciones Web Push (panel)."""
from typing import Literal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from ...core.config import ajustes
from ..deps import Usuario, usuario_actual

router = APIRouter(tags=["push"])


class Dispositivo(BaseModel):
    token: str = Field(min_length=10, max_length=512)
    plataforma: Literal["ANDROID", "IOS", "WEB"] = "ANDROID"


@router.post("/dispositivos", status_code=204)
async def registrar(datos: Dispositivo, request: Request, usuario: Usuario = Depends(usuario_actual)):
    """Se llama al iniciar sesión y cuando FCM rota el token. Si el token era
    de otro usuario (celular compartido entre turnos), pasa al usuario actual."""
    async with request.app.state.db.tx() as conn:
        await conn.execute("""
            INSERT INTO dispositivo_push (usuario_id, token, plataforma) VALUES (%s, %s, %s)
            ON CONFLICT (token) DO UPDATE SET usuario_id = EXCLUDED.usuario_id,
                                              plataforma = EXCLUDED.plataforma, actualizado_en = now()""",
                           [usuario.id, datos.token, datos.plataforma])


@router.delete("/dispositivos/{token}", status_code=204)
async def eliminar(token: str, request: Request, usuario: Usuario = Depends(usuario_actual)):
    async with request.app.state.db.tx() as conn:
        await conn.execute("DELETE FROM dispositivo_push WHERE token = %s AND usuario_id = %s", [token, usuario.id])


@router.get("/webpush/clave")
async def clave_publica():
    """Clave VAPID pública para `pushManager.subscribe` en el navegador."""
    return {"clave_publica": ajustes().vapid_publica, "habilitado": bool(ajustes().vapid_publica)}


class Llaves(BaseModel):
    p256dh: str
    auth: str


class Suscripcion(BaseModel):
    endpoint: str = Field(min_length=10, max_length=2000)
    keys: Llaves


@router.post("/webpush/suscripciones", status_code=204)
async def suscribir(datos: Suscripcion, request: Request, usuario: Usuario = Depends(usuario_actual)):
    async with request.app.state.db.tx() as conn:
        await conn.execute("""
            INSERT INTO web_push_suscripcion (usuario_id, endpoint, p256dh, auth, user_agent)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (endpoint) DO UPDATE SET usuario_id = EXCLUDED.usuario_id, p256dh = EXCLUDED.p256dh,
                                                 auth = EXCLUDED.auth""",
                           [usuario.id, datos.endpoint, datos.keys.p256dh, datos.keys.auth,
                            (request.headers.get("user-agent") or "")[:255]])


class Baja(BaseModel):
    endpoint: str


@router.post("/webpush/baja", status_code=204)
async def desuscribir(datos: Baja, request: Request, usuario: Usuario = Depends(usuario_actual)):
    async with request.app.state.db.tx() as conn:
        await conn.execute("DELETE FROM web_push_suscripcion WHERE endpoint = %s AND usuario_id = %s",
                           [datos.endpoint, usuario.id])
