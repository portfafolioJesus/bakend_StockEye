from fastapi import APIRouter, Request

from ... import __version__
from ...core.db import todos, uno

router = APIRouter(tags=["salud"])


@router.get("/salud")
async def salud(request: Request):
    """Para healthchecks y monitoreo: BD, cola de inferencia y modelo activo."""
    async with request.app.state.db.tx() as conn:
        cola = await todos(conn, """
            SELECT r.codigo AS recinto, i.estado::text AS estado, count(*) AS n
              FROM imagen i JOIN recinto r ON r.id = i.recinto_id
             WHERE i.estado IN ('PENDIENTE', 'PROCESANDO')
                OR (i.estado = 'ERROR' AND i.recibida_en > now() - interval '1 day')
             GROUP BY 1, 2""")
        modelo = await uno(conn, "SELECT nombre, version, familia FROM modelo_ia WHERE activo")
        latencia = await uno(conn, """
            SELECT percentile_cont(0.95) WITHIN GROUP (ORDER BY EXTRACT(EPOCH FROM procesada_en - recibida_en))
                       AS p95_espera_s,
                   percentile_cont(0.95) WITHIN GROUP (ORDER BY p.tiempo_inferencia_ms) AS p95_inferencia_ms
              FROM imagen i JOIN prediccion p ON p.imagen_id = i.id
             WHERE i.procesada_en > now() - interval '1 hour'""")
    return {"estado": "ok", "servicio": "stockeye-api", "version": __version__, "modelo_activo": modelo,
            "cola": cola, "ultima_hora": latencia}
