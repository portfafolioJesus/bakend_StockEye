"""Consultas compartidas entre routers (detalle de imagen con su predicción)."""
from __future__ import annotations

from ..core.almacenamiento import ruta_anotada
from ..core.db import todos, uno
from ..core.seguridad import url_firmada


async def estado_ia(conn, imagen_id: int) -> dict:
    a = await uno(conn, """SELECT proveedor, modelo, productos_faltantes, resumen, exitoso, error_detalle, creado_en
                             FROM analisis_ia WHERE imagen_id = %s ORDER BY creado_en DESC LIMIT 1""", [imagen_id])
    if a:
        return {"estado": "lista" if a["exitoso"] else "error", "productos": a["productos_faltantes"] or [],
                "resumen": a["resumen"], "proveedor": a["proveedor"], "modelo": a["modelo"],
                "error": a["error_detalle"]}
    pendiente = await uno(conn, """SELECT 1 FROM tarea WHERE tipo = 'ANALISIS_IA' AND estado IN ('PENDIENTE','PROCESANDO')
                                     AND (payload ->> 'imagen_id')::BIGINT = %s""", [imagen_id])
    if pendiente:
        return {"estado": "pendiente", "productos": []}
    activa = await uno(conn, "SELECT activo FROM configuracion_ia")
    return {"estado": "no_aplica" if activa and activa["activo"] else "desactivada", "productos": []}


async def detalle_imagen(conn, imagen_id: int) -> dict | None:
    i = await uno(conn, """
        SELECT i.id, i.recinto_id, i.origen, i.estado, i.error_detalle, i.capturada_en, i.recibida_en,
               i.procesada_en, i.ruta_archivo, i.ancho_px, i.alto_px, i.subida_por,
               g.id AS gondola_id, g.codigo AS gondola_codigo, g.categoria, g.pasillo,
               c.codigo AS camara_codigo, cat.id AS categoria_id, cat.nombre AS categoria_nombre
          FROM imagen i
          LEFT JOIN gondola g ON g.id = i.gondola_id
          LEFT JOIN camara c ON c.id = i.camara_id
          LEFT JOIN categoria cat ON cat.id = i.categoria_id
         WHERE i.id = %s""", [imagen_id])
    if not i:
        return None
    p = await uno(conn, """
        SELECT p.id, p.porcentaje_vacio, p.umbral_aplicado, p.supera_umbral, p.num_vacios, p.num_productos,
               p.tiempo_inferencia_ms, p.ruta_imagen_anotada, p.creada_en,
               m.nombre || ' ' || m.version AS modelo
          FROM prediccion p JOIN modelo_ia m ON m.id = p.modelo_id
         WHERE p.imagen_id = %s ORDER BY p.creada_en DESC LIMIT 1""", [imagen_id])
    detecciones = []
    if p:
        detecciones = await todos(conn, """SELECT clase, confianza, x_min, y_min, x_max, y_max
                                             FROM deteccion WHERE prediccion_id = %s ORDER BY confianza DESC""",
                                  [p["id"]])
    ticket = await uno(conn, """SELECT t.numero, ti.tipo FROM ticket_imagen ti JOIN ticket t ON t.id = ti.ticket_id
                                 WHERE ti.imagen_id = %s ORDER BY ti.agregada_en LIMIT 1""", [imagen_id])
    anotada = (p or {}).get("ruta_imagen_anotada") or (ruta_anotada(i["ruta_archivo"]) if p else None)
    return {
        "id": i["id"], "recinto_id": i["recinto_id"], "origen": i["origen"], "estado": i["estado"],
        "error": i["error_detalle"], "capturada_en": i["capturada_en"], "recibida_en": i["recibida_en"],
        "procesada_en": i["procesada_en"], "ancho_px": i["ancho_px"], "alto_px": i["alto_px"],
        "ruta": i["ruta_archivo"], "url": url_firmada(i["ruta_archivo"]), "url_anotada": url_firmada(anotada),
        "gondola": {"id": i["gondola_id"], "codigo": i["gondola_codigo"], "categoria": i["categoria"],
                    "pasillo": i["pasillo"]} if i["gondola_id"] else None,
        "camara_codigo": i["camara_codigo"],
        "categoria": {"id": i["categoria_id"], "nombre": i["categoria_nombre"]} if i["categoria_id"] else None,
        "prediccion": {k: p[k] for k in ("porcentaje_vacio", "umbral_aplicado", "supera_umbral", "num_vacios",
                                         "num_productos", "tiempo_inferencia_ms", "modelo", "creada_en")} if p else None,
        "detecciones": detecciones,
        "ia": await estado_ia(conn, imagen_id) if p else {"estado": "pendiente", "productos": []},
        "ticket": ticket,
    }
