"""Indicadores básicos por recinto."""
from fastapi import APIRouter, Depends, Query, Request

from ...core.db import todos, uno
from ..deps import ADMIN, SUPERVISOR, Usuario, exigir_recinto, requiere

router = APIRouter(prefix="/reportes", tags=["reportes"])


@router.get("")
async def reporte(request: Request, recinto_id: int, dias: int = Query(14, ge=1, le=180),
                  u: Usuario = Depends(requiere(ADMIN, SUPERVISOR))):
    exigir_recinto(u, recinto_id)
    async with request.app.state.db.tx() as conn:
        por_dia = await todos(conn, """
            SELECT d::date AS dia,
                   (SELECT count(*) FROM ticket t WHERE t.recinto_id = %(r)s
                       AND (t.creado_en AT TIME ZONE 'America/Santiago')::date = d::date) AS abiertos,
                   (SELECT count(*) FROM ticket t WHERE t.recinto_id = %(r)s AND t.estado = 'CERRADO'
                       AND (t.cerrado_en AT TIME ZONE 'America/Santiago')::date = d::date) AS cerrados
              FROM generate_series((now() AT TIME ZONE 'America/Santiago')::date - (%(d)s - 1),
                                   (now() AT TIME ZONE 'America/Santiago')::date, interval '1 day') d
             ORDER BY d""", {"r": recinto_id, "d": dias})
        totales = await uno(conn, """
            SELECT count(*) AS tickets,
                   count(*) FILTER (WHERE estado = 'CERRADO') AS cerrados,
                   count(*) FILTER (WHERE estado = 'CERRADO' AND cierre_verificado) AS cerrados_verificados,
                   round(avg(minutos_abierto) FILTER (WHERE estado = 'CERRADO')) AS minutos_promedio_cierre,
                   round(avg(EXTRACT(EPOCH FROM asignado_en - creado_en) / 60)
                         FILTER (WHERE asignado_en IS NOT NULL)) AS minutos_promedio_asignacion,
                   round(avg(porcentaje_vacio), 1) AS vacio_promedio
              FROM v_ticket_resumen
             WHERE recinto_id = %(r)s AND creado_en > now() - make_interval(days => %(d)s)""",
                           {"r": recinto_id, "d": dias})
        por_categoria = await todos(conn, """
            SELECT COALESCE(categoria, 'Sin categoría') AS categoria, count(*) AS tickets,
                   round(avg(porcentaje_vacio), 1) AS vacio_promedio
              FROM v_ticket_resumen
             WHERE recinto_id = %(r)s AND creado_en > now() - make_interval(days => %(d)s)
             GROUP BY 1 ORDER BY 2 DESC LIMIT 10""", {"r": recinto_id, "d": dias})
    return {"dias": dias, "por_dia": por_dia, "totales": totales, "por_categoria": por_categoria}
