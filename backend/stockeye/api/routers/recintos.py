"""Recintos vistos por supervisores y reponedores: equipo, góndolas, cámaras y alertas."""
from fastapi import APIRouter, Depends, Query, Request

from ...core.db import todos
from ..deps import Usuario, exigir_recinto, recintos_visibles, usuario_actual

router = APIRouter(prefix="/recintos", tags=["recintos"])


@router.get("")
async def listar(request: Request, usuario: Usuario = Depends(usuario_actual)):
    visibles = recintos_visibles(usuario)
    async with request.app.state.db.tx() as conn:
        return await todos(conn, """
            SELECT r.id, r.codigo, r.nombre, r.comuna, r.carpeta_imagenes, r.umbral_vacio,
                   (SELECT count(*) FROM v_camara_estado c WHERE c.recinto_id = r.id AND c.activa AND c.tipo = 'IP') AS camaras,
                   (SELECT count(*) FROM v_camara_estado c WHERE c.recinto_id = r.id AND c.en_linea AND c.tipo = 'IP') AS camaras_en_linea
              FROM recinto r
             WHERE r.activo AND (%s::int[] IS NULL OR r.id = ANY(%s::int[]))
             ORDER BY r.codigo""", [visibles, visibles])


@router.get("/{recinto_id}/equipo")
async def equipo(recinto_id: int, request: Request, usuario: Usuario = Depends(usuario_actual)):
    """Panel "Equipo de turno": carga de cada reponedor del recinto."""
    exigir_recinto(usuario, recinto_id)
    async with request.app.state.db.tx() as conn:
        return await todos(conn, """
            SELECT v.usuario_id, v.reponedor, v.asignados, v.en_progreso, v.cerrados_hoy,
                   u.ultimo_acceso, u.ultimo_acceso_origen
              FROM v_carga_reponedor v JOIN usuario u ON u.id = v.usuario_id
             WHERE v.recinto_id = %s
             ORDER BY v.asignados + v.en_progreso DESC, v.reponedor""", [recinto_id])


@router.get("/{recinto_id}/gondolas")
async def gondolas(recinto_id: int, request: Request, usuario: Usuario = Depends(usuario_actual)):
    """Selector de góndola de la app (el QR de la góndola contiene su código)."""
    exigir_recinto(usuario, recinto_id)
    async with request.app.state.db.tx() as conn:
        return await todos(conn, """
            SELECT g.id, g.codigo, g.pasillo, g.categoria, g.categoria_id, g.descripcion,
                   (SELECT c.codigo FROM camara c WHERE c.gondola_id = g.id AND c.activa AND c.tipo = 'IP' LIMIT 1) AS camara_codigo
              FROM gondola g LEFT JOIN categoria c ON c.id = g.categoria_id
             WHERE g.recinto_id = %s AND g.activo ORDER BY c.orden NULLS LAST, g.codigo""", [recinto_id])


@router.get("/{recinto_id}/categorias")
async def categorias_del_recinto(recinto_id: int, request: Request, usuario: Usuario = Depends(usuario_actual)):
    """Categorías con sus tickets activos y puntos fijos en este recinto."""
    exigir_recinto(usuario, recinto_id)
    async with request.app.state.db.tx() as conn:
        return await todos(conn, """
            SELECT c.id, c.codigo, c.nombre, c.departamento,
                   (SELECT count(*) FROM v_ticket_resumen t WHERE t.recinto_id = %(r)s AND t.categoria_id = c.id
                       AND t.estado IN ('ABIERTO','ASIGNADO','EN_PROGRESO')) AS tickets_activos,
                   (SELECT round(avg(p.porcentaje_vacio), 1) FROM imagen i JOIN prediccion p ON p.imagen_id = i.id
                     WHERE i.recinto_id = %(r)s AND i.categoria_id = c.id
                       AND i.capturada_en > now() - interval '7 days') AS vacio_promedio_7d,
                   (SELECT max(i.capturada_en) FROM imagen i WHERE i.recinto_id = %(r)s AND i.categoria_id = c.id) AS ultima_foto,
                   COALESCE((SELECT json_agg(json_build_object('id', g.id, 'codigo', g.codigo, 'descripcion', g.descripcion)
                                             ORDER BY g.codigo)
                               FROM gondola g WHERE g.recinto_id = %(r)s AND g.categoria_id = c.id AND g.activo), '[]') AS puntos
              FROM categoria c WHERE c.activo
             ORDER BY c.orden, c.nombre""", {"r": recinto_id})


@router.get("/{recinto_id}/camaras")
async def camaras(recinto_id: int, request: Request, usuario: Usuario = Depends(usuario_actual)):
    exigir_recinto(usuario, recinto_id)
    async with request.app.state.db.tx() as conn:
        return await todos(conn, """SELECT * FROM v_camara_estado WHERE recinto_id = %s AND tipo = 'IP' ORDER BY codigo""",
                           [recinto_id])


@router.get("/{recinto_id}/alertas")
async def alertas(recinto_id: int, request: Request, usuario: Usuario = Depends(usuario_actual),
                  limite: int = Query(10, ge=1, le=50)):
    """Panel "Últimas alertas": aperturas y seguimientos con el % y el anterior."""
    exigir_recinto(usuario, recinto_id)
    async with request.app.state.db.tx() as conn:
        return await todos(conn, """
            WITH ev AS (
                SELECT t.numero, ti.tipo, i.capturada_en AS en, p.porcentaje_vacio,
                       g.codigo AS gondola_codigo, g.categoria,
                       lag(p.porcentaje_vacio) OVER (PARTITION BY t.id ORDER BY i.capturada_en) AS anterior
                  FROM ticket t
                  JOIN ticket_imagen ti ON ti.ticket_id = t.id AND ti.tipo IN ('APERTURA', 'SEGUIMIENTO')
                  JOIN imagen i ON i.id = ti.imagen_id
                  JOIN prediccion p ON p.imagen_id = i.id
                  LEFT JOIN gondola g ON g.id = t.gondola_id
                 WHERE t.recinto_id = %s AND i.capturada_en > now() - interval '2 days')
            SELECT * FROM ev ORDER BY en DESC LIMIT %s""", [recinto_id, limite])
