"""Tiempo real para el panel web con Server-Sent Events.

EventSource no permite headers, así que el token va en ?token=. Solo se
envían eventos de los recintos del usuario y sus propias notificaciones.
"""
import asyncio
import json

from fastapi import APIRouter, Query, Request
from fastapi.responses import StreamingResponse

from ..deps import recintos_visibles, usuario_desde_token
from ..eventos import Suscriptor

router = APIRouter(tags=["tiempo real"])
NOMBRES = {"ticket_evento": "ticket", "notificacion_nueva": "notificacion", "imagen_procesada": "imagen"}


@router.get("/eventos")
async def eventos(request: Request, token: str = Query(...)):
    usuario = await usuario_desde_token(request.app.state.db, token)
    visibles = recintos_visibles(usuario)
    sub = Suscriptor(usuario.id, None if visibles is None else set(visibles))
    hub = request.app.state.hub
    hub.suscribir(sub)

    async def flujo():
        try:
            yield "retry: 5000\n\n"
            while True:
                if await request.is_disconnected():
                    break
                try:
                    canal, datos = await asyncio.wait_for(sub.cola.get(), timeout=20)
                except asyncio.TimeoutError:
                    yield ": ping\n\n"          # mantiene viva la conexión a través de proxies
                    continue
                yield f"event: {NOMBRES.get(canal, canal)}\ndata: {json.dumps(datos, default=str)}\n\n"
        finally:
            hub.desuscribir(sub)

    return StreamingResponse(flujo(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
