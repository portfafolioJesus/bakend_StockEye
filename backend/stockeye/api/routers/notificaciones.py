from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel

from ...core.db import todos, uno, valor
from ..deps import Usuario, usuario_actual

router = APIRouter(prefix="/notificaciones", tags=["notificaciones"])


@router.get("")
async def listar(request: Request, usuario: Usuario = Depends(usuario_actual),
                 solo_no_leidas: bool = False, limite: int = Query(30, ge=1, le=100)):
    async with request.app.state.db.tx() as conn:
        filas = await todos(conn, """
            SELECT n.id, n.tipo, n.mensaje, n.leida, n.creada_en, t.numero AS ticket_numero, n.incidente_ia_id,
                   (SELECT ar.recinto_id FROM incidencia_ia_recinto ar JOIN usuario_recinto ur ON ur.recinto_id=ar.recinto_id
                     WHERE ar.incidencia_id=n.incidente_ia_id AND ur.usuario_id=n.usuario_id ORDER BY ar.recinto_id LIMIT 1) AS recinto_id
              FROM notificacion n LEFT JOIN ticket t ON t.id = n.ticket_id
             WHERE n.usuario_id = %s AND (NOT %s OR NOT n.leida)
             ORDER BY n.creada_en DESC LIMIT %s""", [usuario.id, solo_no_leidas, limite])
        no_leidas = await valor(conn, "SELECT count(*) FROM notificacion WHERE usuario_id = %s AND NOT leida",
                                [usuario.id])
    return {"no_leidas": no_leidas, "notificaciones": filas}


class Marca(BaseModel):
    leida: bool = True


@router.patch("/{notificacion_id}")
async def marcar(notificacion_id: int, datos: Marca, request: Request, usuario: Usuario = Depends(usuario_actual)):
    async with request.app.state.db.tx() as conn:
        n = await uno(conn, """UPDATE notificacion SET leida = %s WHERE id = %s AND usuario_id = %s
                               RETURNING id, leida""", [datos.leida, notificacion_id, usuario.id])
    if not n:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Notificación no encontrada")
    return n


@router.post("/leer-todas", status_code=204)
async def leer_todas(request: Request, usuario: Usuario = Depends(usuario_actual)):
    async with request.app.state.db.tx() as conn:
        await conn.execute("UPDATE notificacion SET leida = TRUE WHERE usuario_id = %s AND NOT leida", [usuario.id])
