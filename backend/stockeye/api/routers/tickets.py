"""Tickets: bandeja, detalle, creación, asignación, estados, comentarios y cierre."""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile, status
from pydantic import BaseModel, Field

from ...core.almacenamiento import ruta_anotada
from ...core.db import todos, uno, valor
from ...core.seguridad import url_firmada
from ..deps import ADMIN, REPONEDOR, SUPERVISOR, Usuario, exigir_recinto, recintos_visibles, requiere, usuario_actual
from .imagenes import Destino, registrar_foto_movil

router = APIRouter(prefix="/tickets", tags=["tickets"])

Estado = Literal["ABIERTO", "ASIGNADO", "EN_PROGRESO", "CERRADO", "CANCELADO"]
Prioridad = Literal["BAJA", "MEDIA", "ALTA", "CRITICA"]
ESTADOS_ACTIVOS = ("ABIERTO", "ASIGNADO", "EN_PROGRESO")
NOMBRE_ESTADO = {"ABIERTO": "Abierto", "ASIGNADO": "Asignado", "EN_PROGRESO": "En progreso",
                 "CERRADO": "Cerrado", "CANCELADO": "Cancelado"}
COLUMNAS = """id, numero, titulo, estado, prioridad, origen, porcentaje_vacio, producto_faltante, enriquecido_ia,
    recinto_id, recinto_codigo, gondola_id, gondola_codigo, pasillo, categoria, categoria_producto, descripcion,
    asignado_a, asignado_nombre, asignado_por_nombre, creado_por, creado_por_nombre, creado_en, asignado_en,
    cerrado_en, actualizado_en, minutos_abierto, num_comentarios, cierre_verificado, camara_codigo,
    pct_apertura, pct_cierre, umbral_vacio, camara_tipo, categoria_id, departamento"""
HOY = "(cerrado_en AT TIME ZONE 'America/Santiago')::date = (now() AT TIME ZONE 'America/Santiago')::date"


def _pct(v) -> str:
    return f"{float(v):.1f}".replace(".", ",") + " %" if v is not None else "—"


# ---------------------------------------------------------------- bandeja

@router.get("")
async def listar(request: Request, usuario: Usuario = Depends(usuario_actual),
                 recinto_id: int | None = None,
                 estado: str | None = Query(None, description="Uno o varios separados por coma"),
                 prioridad: str | None = None,
                 vista: Literal["todos", "sin_asignar", "asignados", "en_progreso", "cerrados_hoy", "activos",
                                "historial"] = "todos",
                 asignado: str | None = Query(None, description="'me', 'sin' o id de usuario"),
                 categoria_id: int | None = None,
                 q: str | None = Query(None, max_length=80),
                 limite: int = Query(100, ge=1, le=500), desde: int = Query(0, ge=0)):
    filtros, params = [], []
    visibles = recintos_visibles(usuario)
    if recinto_id is not None:
        exigir_recinto(usuario, recinto_id)
        filtros.append("recinto_id = %s"); params.append(recinto_id)
    elif visibles is not None:
        filtros.append("recinto_id = ANY(%s)"); params.append(visibles)
    if categoria_id:
        filtros.append("categoria_id = %s"); params.append(categoria_id)
    if usuario.rol == REPONEDOR:                      # el reponedor ve los que se le asignaron y los que él reportó
        filtros.append("(asignado_a = %s OR creado_por = %s)"); params.append(usuario.id); params.append(usuario.id)
    elif asignado == "me":
        filtros.append("asignado_a = %s"); params.append(usuario.id)
    elif asignado == "sin":
        filtros.append("asignado_a IS NULL")
    elif asignado and asignado.isdigit():
        filtros.append("asignado_a = %s"); params.append(int(asignado))
    base_filtros, base_params = list(filtros), list(params)     # para los conteos de las tarjetas

    vistas = {"sin_asignar": "estado = 'ABIERTO'", "asignados": "estado = 'ASIGNADO'",
              "en_progreso": "estado = 'EN_PROGRESO'", "cerrados_hoy": f"estado = 'CERRADO' AND {HOY}",
              "activos": "estado IN ('ABIERTO','ASIGNADO','EN_PROGRESO')",
              # "Todos" de la bandeja = lo del turno (activos + cerrados hoy); "historial" = sin filtro
              "todos": f"(estado IN ('ABIERTO','ASIGNADO','EN_PROGRESO') OR (estado = 'CERRADO' AND {HOY}))"}
    if vista == "todos" and (q or estado):
        vista = "historial"                                       # al buscar se mira todo
    if vista in vistas:
        filtros.append(vistas[vista])
    if estado:
        filtros.append("estado::text = ANY(%s)"); params.append([e.strip().upper() for e in estado.split(",")])
    if prioridad:
        filtros.append("prioridad::text = ANY(%s)"); params.append([p.strip().upper() for p in prioridad.split(",")])
    if q:
        filtros.append("""(numero ILIKE %s OR titulo ILIKE %s OR gondola_codigo ILIKE %s
                           OR producto_faltante ILIKE %s OR categoria ILIKE %s)""")
        params += [f"%{q.strip()}%"] * 5
    where = " AND ".join(filtros) or "TRUE"
    where_base = " AND ".join(base_filtros) or "TRUE"

    async with request.app.state.db.tx() as conn:
        filas = await todos(conn, f"""
            SELECT {COLUMNAS} FROM v_ticket_resumen WHERE {where}
             ORDER BY CASE estado WHEN 'ABIERTO' THEN 0 WHEN 'ASIGNADO' THEN 1 WHEN 'EN_PROGRESO' THEN 1
                                  WHEN 'CERRADO' THEN 3 ELSE 4 END,
                      prioridad DESC, creado_en DESC
             LIMIT %s OFFSET %s""", params + [limite, desde])
        total = await valor(conn, f"SELECT count(*) FROM v_ticket_resumen WHERE {where}", params)
        conteos = await uno(conn, f"""
            SELECT count(*) FILTER (WHERE estado = 'ABIERTO')                 AS sin_asignar,
                   count(*) FILTER (WHERE estado = 'ASIGNADO')                AS asignados,
                   count(*) FILTER (WHERE estado = 'EN_PROGRESO')             AS en_progreso,
                   count(*) FILTER (WHERE estado = 'CERRADO' AND {HOY})       AS cerrados_hoy,
                   count(*) FILTER (WHERE estado = 'CERRADO' AND {HOY} AND cierre_verificado) AS cerrados_hoy_verificados,
                   count(*) FILTER (WHERE estado IN ('ABIERTO','ASIGNADO','EN_PROGRESO')) AS activos,
                   count(*) FILTER (WHERE estado IN ('ABIERTO','ASIGNADO','EN_PROGRESO') OR {HOY}) AS todos,
                   max(minutos_abierto) FILTER (WHERE estado = 'ABIERTO')     AS sin_asignar_mas_antiguo_min
              FROM v_ticket_resumen WHERE {where_base}""", base_params)
    return {"total": total, "conteos": conteos, "tickets": filas}


# ---------------------------------------------------------------- detalle

async def _ticket(conn, numero: str, usuario: Usuario) -> dict:
    t = await uno(conn, f"SELECT {COLUMNAS} FROM v_ticket_resumen WHERE numero = %s", [numero.upper()])
    if not t:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ticket no encontrado")
    exigir_recinto(usuario, t["recinto_id"])
    return t


def _permisos(t: dict, usuario: Usuario) -> dict:
    gestiona = usuario.rol in (SUPERVISOR, ADMIN)
    propio = t["asignado_a"] == usuario.id
    activo = t["estado"] in ESTADOS_ACTIVOS
    return {"asignar": gestiona and activo, "editar": (gestiona or propio) and t["estado"] != "CANCELADO",
            "empezar": propio and t["estado"] == "ASIGNADO",
            "cerrar": (propio or gestiona) and t["estado"] in ("ASIGNADO", "EN_PROGRESO"),
            "cancelar": gestiona and activo, "cambiar_estado": gestiona, "comentar": True}


async def detalle(conn, numero: str, usuario: Usuario) -> dict:
    t = await _ticket(conn, numero, usuario)
    evid = await todos(conn, """
        SELECT ti.imagen_id, ti.tipo, ti.agregada_en, i.capturada_en, i.origen, i.estado AS estado_imagen,
               i.ruta_archivo, c.codigo AS camara_codigo, c.tipo AS camara_tipo,
               p.porcentaje_vacio, p.umbral_aplicado, p.supera_umbral, p.num_vacios, p.tiempo_inferencia_ms,
               p.ruta_imagen_anotada, m.nombre || ' ' || m.version AS modelo,
               u.nombre || ' ' || u.apellido AS subida_por_nombre
          FROM ticket_imagen ti
          JOIN imagen i ON i.id = ti.imagen_id
          LEFT JOIN camara c ON c.id = i.camara_id
          LEFT JOIN usuario u ON u.id = i.subida_por
          LEFT JOIN LATERAL (SELECT * FROM prediccion WHERE imagen_id = i.id ORDER BY creada_en DESC LIMIT 1) p ON TRUE
          LEFT JOIN modelo_ia m ON m.id = p.modelo_id
         WHERE ti.ticket_id = %s
         ORDER BY i.capturada_en""", [t["id"]])
    for e in evid:
        anotada = e.pop("ruta_imagen_anotada") or (ruta_anotada(e["ruta_archivo"]) if e["porcentaje_vacio"] is not None else None)
        e["url"], e["url_anotada"] = url_firmada(e["ruta_archivo"]), url_firmada(anotada)
        e["detecciones"] = await todos(conn, """
            SELECT d.clase, d.confianza, d.x_min, d.y_min, d.x_max, d.y_max
              FROM deteccion d JOIN prediccion p ON p.id = d.prediccion_id
             WHERE p.imagen_id = %s ORDER BY d.confianza DESC""", [e["imagen_id"]])
    comentarios = await todos(conn, """
        SELECT c.id, c.usuario_id, u.nombre || ' ' || u.apellido AS nombre, u.rol, c.texto, c.creado_en
          FROM comentario c JOIN usuario u ON u.id = c.usuario_id
         WHERE c.ticket_id = %s ORDER BY c.creado_en""", [t["id"]])
    historial = await todos(conn, """
        SELECT h.creado_en, h.estado_anterior, h.estado_nuevo, h.asignado_anterior, h.asignado_nuevo,
               u.nombre || ' ' || u.apellido AS actor, an.nombre || ' ' || an.apellido AS asignado_nombre
          FROM historial_ticket h
          LEFT JOIN usuario u  ON u.id  = h.usuario_id
          LEFT JOIN usuario an ON an.id = h.asignado_nuevo
         WHERE h.ticket_id = %s ORDER BY h.creado_en""", [t["id"]])
    analisis = await uno(conn, """
        SELECT a.proveedor, a.modelo, a.productos_faltantes, a.resumen, a.exitoso, a.creado_en, a.latencia_ms
          FROM analisis_ia a
         WHERE a.ticket_id = %s OR a.imagen_id IN (SELECT imagen_id FROM ticket_imagen WHERE ticket_id = %s AND tipo = 'APERTURA')
         ORDER BY a.exitoso DESC, a.creado_en DESC LIMIT 1""", [t["id"], t["id"]])
    ia_pendiente = await valor(conn, """
        SELECT EXISTS (SELECT 1 FROM tarea WHERE tipo = 'ANALISIS_IA' AND estado IN ('PENDIENTE','PROCESANDO')
                         AND (payload ->> 'ticket_id')::BIGINT = %s)""", [t["id"]])
    equipo = []
    if usuario.rol in (SUPERVISOR, ADMIN):
        equipo = await todos(conn, """SELECT usuario_id, reponedor, asignados, en_progreso, cerrados_hoy
                                        FROM v_carga_reponedor WHERE recinto_id = %s
                                       ORDER BY asignados + en_progreso, reponedor""", [t["recinto_id"]])
    return {"ticket": t, "evidencias": evid, "comentarios": comentarios,
            "linea_tiempo": _linea_tiempo(t, historial, evid, analisis),
            "ia": analisis, "ia_pendiente": ia_pendiente, "equipo": equipo, "permisos": _permisos(t, usuario)}


def _linea_tiempo(t: dict, historial: list, evid: list, analisis: dict | None) -> list[dict]:
    eventos = []
    apertura = next((e for e in evid if e["tipo"] == "APERTURA"), None)
    for h in historial:
        actor = h["actor"]
        if h["estado_anterior"] is None:
            if actor:
                texto = f"{actor} creó el ticket"
            elif apertura and apertura.get("camara_tipo") == "CARGA":
                texto = (f"El sistema abrió el ticket con una foto cargada: el modelo detectó "
                         f"{_pct(apertura['porcentaje_vacio'])} de vacío. Alerta enviada a supervisión.")
            elif apertura and apertura["camara_codigo"]:
                texto = (f"El sistema abrió el ticket: {apertura['camara_codigo']} detectó "
                         f"{_pct(apertura['porcentaje_vacio'])} de vacío. Alerta enviada a supervisión.")
            else:
                texto = "El sistema abrió el ticket"
            eventos.append(dict(en=h["creado_en"], tipo="apertura", texto=texto))
            continue
        if h["asignado_nuevo"] != h["asignado_anterior"] and h["asignado_nuevo"]:
            eventos.append(dict(en=h["creado_en"], tipo="asignacion",
                                texto=f"{actor or 'El sistema'} asignó el ticket a {h['asignado_nombre']}"))
        elif h["asignado_nuevo"] is None and h["asignado_anterior"]:
            eventos.append(dict(en=h["creado_en"], tipo="asignacion", texto=f"{actor or 'El sistema'} quitó la asignación"))
        if h["estado_nuevo"] != h["estado_anterior"] and not (h["estado_anterior"] == "ABIERTO" and h["estado_nuevo"] == "ASIGNADO"):
            eventos.append(dict(en=h["creado_en"], tipo="estado",
                                texto=f"{actor or 'El sistema'} cambió el estado a {NOMBRE_ESTADO[h['estado_nuevo']]}"))
    anterior = apertura["porcentaje_vacio"] if apertura else None
    for e in evid:
        if e["tipo"] == "SEGUIMIENTO":
            fuente = "cargada" if e.get("camara_tipo") == "CARGA" else "de la cámara"
            texto = f"Nueva foto {fuente}: {_pct(e['porcentaje_vacio'])}"
            if anterior is not None and e["porcentaje_vacio"] is not None and e["porcentaje_vacio"] > anterior:
                texto += f" (sube desde {_pct(anterior)})"
            eventos.append(dict(en=e["capturada_en"], tipo="seguimiento", texto=texto))
            anterior = e["porcentaje_vacio"] if e["porcentaje_vacio"] is not None else anterior
        elif e["tipo"] == "CIERRE":
            if e["porcentaje_vacio"] is None:
                texto = "Foto de verificación en análisis…"
            elif e["supera_umbral"]:
                texto = f"Foto de verificación: {_pct(e['porcentaje_vacio'])}, aún sobre el umbral"
            else:
                texto = f"Foto de verificación: {_pct(e['porcentaje_vacio'])}, bajo el umbral (cierre verificado)"
            eventos.append(dict(en=e["capturada_en"], tipo="cierre", texto=texto))
    if analisis and analisis["exitoso"] and analisis["productos_faltantes"]:
        top = analisis["productos_faltantes"][0]
        conf = f" ({round(float(top.get('confianza', 0)) * 100)} %)" if top.get("confianza") is not None else ""
        eventos.append(dict(en=analisis["creado_en"], tipo="ia",
                            texto=f"La IA identificó el producto faltante: {top.get('producto')}{conf}"))
    eventos.sort(key=lambda e: e["en"], reverse=True)
    return eventos


@router.get("/{numero}")
async def obtener(numero: str, request: Request, usuario: Usuario = Depends(usuario_actual)):
    async with request.app.state.db.tx() as conn:
        return await detalle(conn, numero, usuario)


# ---------------------------------------------------------------- crear

class NuevoTicket(BaseModel):
    imagen_id: int | None = None                  # flujo móvil: "Crear ticket" tras ver el resultado
    recinto_id: int | None = None
    gondola_id: int | None = None
    categoria_id: int | None = None
    titulo: str | None = Field(None, max_length=150)
    descripcion: str | None = Field(None, max_length=4000)
    producto_faltante: str | None = Field(None, max_length=150)
    categoria_producto: str | None = Field(None, max_length=80)
    prioridad: Prioridad | None = None
    comentario: str | None = Field(None, max_length=2000)
    asignado_a: int | None = None


@router.post("", status_code=201)
async def crear(datos: NuevoTicket, request: Request,
                usuario: Usuario = Depends(requiere(REPONEDOR, SUPERVISOR, ADMIN))):
    async with request.app.state.db.tx(usuario.id) as conn:
        if datos.imagen_id:
            ticket_id = await _crear_desde_imagen(conn, datos, usuario)
        else:
            ticket_id = await _crear_manual(conn, datos, usuario)
        campos, params = [], []
        for campo in ("titulo", "descripcion", "producto_faltante", "categoria_producto", "prioridad"):
            v = getattr(datos, campo)
            if v not in (None, ""):
                campos.append(f"{campo} = %s"); params.append(v.strip() if isinstance(v, str) else v)
        if campos:
            await conn.execute(f"UPDATE ticket SET {', '.join(campos)} WHERE id = %s", params + [ticket_id])
        if datos.imagen_id:
            # Enlaza el análisis de IA de la foto (o lo encola si aún no existe).
            await conn.execute("SELECT fn_encolar_analisis_ia(%s, %s)", [datos.imagen_id, ticket_id])
            if datos.producto_faltante:
                await conn.execute("""
                    UPDATE ticket t SET enriquecido_ia = EXISTS (
                        SELECT 1 FROM analisis_ia a
                         WHERE a.imagen_id = %s AND a.exitoso
                           AND lower(a.productos_faltantes -> 0 ->> 'producto') = lower(t.producto_faltante))
                     WHERE t.id = %s""", [datos.imagen_id, ticket_id])
        if datos.comentario and datos.comentario.strip():
            await conn.execute("INSERT INTO comentario (ticket_id, usuario_id, texto) VALUES (%s, %s, %s)",
                               [ticket_id, usuario.id, datos.comentario.strip()])
        numero = await valor(conn, "SELECT numero FROM ticket WHERE id = %s", [ticket_id])
        return await detalle(conn, numero, usuario)


async def _crear_desde_imagen(conn, datos: NuevoTicket, usuario: Usuario) -> int:
    i = await uno(conn, """
        SELECT i.id, i.recinto_id, i.origen, i.estado, i.subida_por, i.gondola_id, i.categoria_id,
               p.id AS prediccion_id, p.porcentaje_vacio, p.supera_umbral
          FROM imagen i
          LEFT JOIN LATERAL (SELECT * FROM prediccion WHERE imagen_id = i.id ORDER BY creada_en DESC LIMIT 1) p ON TRUE
         WHERE i.id = %s FOR UPDATE OF i""", [datos.imagen_id])
    if not i:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Imagen no encontrada")
    exigir_recinto(usuario, i["recinto_id"])
    if i["origen"] != "MOVIL" or i["subida_por"] != usuario.id or usuario.rol != REPONEDOR:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Solo el reponedor que tomó la foto puede crear el ticket")
    if i["estado"] != "PROCESADA" or i["prediccion_id"] is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "La foto todavía se está analizando")
    if await valor(conn, "SELECT EXISTS (SELECT 1 FROM ticket_imagen WHERE imagen_id = %s)", [i["id"]]):
        raise HTTPException(status.HTTP_409_CONFLICT, "Esa foto ya está asociada a un ticket")
    # Regla de negocio de la BD: abre el ticket a nombre del reponedor (y lo asigna a él)
    ticket_id = await valor(conn, "SELECT fn_ticket_desde_prediccion(%s)", [i["prediccion_id"]])
    if ticket_id is None:
        # Bajo el umbral: el reponedor igual puede reportarlo (lo decide él, queda como móvil)
        ticket_id = await valor(conn, """
            INSERT INTO ticket (titulo, descripcion, prioridad, origen, recinto_id, gondola_id, categoria_id,
                                porcentaje_vacio, creado_por, asignado_a)
            SELECT 'Vacío reportado en ' || COALESCE(g.codigo || ' · ' || g.categoria, cat.nombre, 'góndola'),
                   'Reporte del reponedor con foto bajo el umbral del recinto.',
                   fn_prioridad_por_vacio(%s), 'MOVIL', %s, %s, cat.id, %s, %s
              FROM (SELECT 1) x LEFT JOIN gondola g ON g.id = %s
              LEFT JOIN categoria cat ON cat.id = COALESCE(%s, g.categoria_id)
            RETURNING id""", [i["porcentaje_vacio"], i["recinto_id"], i["gondola_id"], i["porcentaje_vacio"],
                              usuario.id, i["gondola_id"], i["categoria_id"]])
        await conn.execute("INSERT INTO ticket_imagen (ticket_id, imagen_id, tipo) VALUES (%s, %s, 'APERTURA')",
                           [ticket_id, i["id"]])
        await _avisar_supervisores(conn, ticket_id)
    return ticket_id


async def _crear_manual(conn, datos: NuevoTicket, usuario: Usuario) -> int:
    recinto_id = datos.recinto_id
    categoria_id = datos.categoria_id
    if datos.gondola_id:
        g = await uno(conn, "SELECT recinto_id, categoria_id FROM gondola WHERE id = %s", [datos.gondola_id])
        if g is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Góndola no encontrada")
        recinto_id, categoria_id = g["recinto_id"], categoria_id or g["categoria_id"]
    if recinto_id is None and len(usuario.recintos) == 1:
        recinto_id = usuario.recintos[0]
    if recinto_id is None:
        raise HTTPException(422, "Indica el recinto o la góndola")
    exigir_recinto(usuario, recinto_id)
    if not datos.titulo:
        raise HTTPException(422, "El título es obligatorio")
    asignado = None if usuario.rol == REPONEDOR else datos.asignado_a      # el reponedor no se auto-asigna
    ticket_id = await valor(conn, """
        INSERT INTO ticket (titulo, prioridad, origen, recinto_id, gondola_id, categoria_id, creado_por, asignado_a)
        VALUES (%s, %s, 'MANUAL', %s, %s, %s, %s, %s) RETURNING id""",
        [datos.titulo.strip(), datos.prioridad or "MEDIA", recinto_id, datos.gondola_id, categoria_id, usuario.id, asignado])
    if usuario.rol == REPONEDOR:
        await _avisar_supervisores(conn, ticket_id)
    return ticket_id


async def _avisar_supervisores(conn, ticket_id: int) -> None:
    await conn.execute("""
        INSERT INTO notificacion (usuario_id, ticket_id, tipo, mensaje)
        SELECT u.id, t.id, 'ALERTA_VACIO', left(format('%%s reportó %%s: %%s', uc.nombre, t.numero, t.titulo), 255)
          FROM ticket t
          JOIN usuario uc ON uc.id = t.creado_por
          JOIN usuario_recinto ur ON ur.recinto_id = t.recinto_id
          JOIN usuario u ON u.id = ur.usuario_id AND u.rol = 'SUPERVISOR' AND u.activo
         WHERE t.id = %s""", [ticket_id])


# ---------------------------------------------------------------- editar / estados

class CambioTicket(BaseModel):
    asignado_a: int | None = None
    estado: Estado | None = None
    prioridad: Prioridad | None = None
    titulo: str | None = Field(None, min_length=3, max_length=150)
    descripcion: str | None = Field(None, max_length=4000)
    producto_faltante: str | None = Field(None, max_length=150)
    categoria_producto: str | None = Field(None, max_length=80)
    comentario: str | None = Field(None, max_length=2000, description="Motivo (cierre sin verificar o cancelación)")


TRANSICIONES_REPONEDOR = {("ASIGNADO", "EN_PROGRESO"), ("EN_PROGRESO", "ASIGNADO")}


@router.patch("/{numero}")
async def editar(numero: str, datos: CambioTicket, request: Request, usuario: Usuario = Depends(usuario_actual)):
    enviados = datos.model_fields_set
    async with request.app.state.db.tx(usuario.id) as conn:
        t = await _ticket(conn, numero, usuario)
        await conn.execute("SELECT 1 FROM ticket WHERE id = %s FOR UPDATE", [t["id"]])
        gestiona = usuario.rol in (SUPERVISOR, ADMIN)
        if not gestiona:
            if t["asignado_a"] != usuario.id:
                raise HTTPException(status.HTTP_403_FORBIDDEN, "Solo puedes editar tus tickets")
            prohibidos = enviados & {"asignado_a", "prioridad", "titulo", "descripcion"}
            if prohibidos:
                raise HTTPException(status.HTTP_403_FORBIDDEN, f"No puedes cambiar: {', '.join(sorted(prohibidos))}")
            if datos.estado and datos.estado != t["estado"] and (t["estado"], datos.estado) not in TRANSICIONES_REPONEDOR:
                if datos.estado == "CERRADO":
                    raise HTTPException(status.HTTP_409_CONFLICT, "Usa 'Cerrar ticket' con la foto de verificación")
                raise HTTPException(status.HTTP_403_FORBIDDEN, "Cambio de estado no permitido")

        campos, params = [], []
        for campo in ("prioridad", "titulo", "descripcion", "producto_faltante", "categoria_producto"):
            if campo in enviados:
                v = getattr(datos, campo)
                campos.append(f"{campo} = %s"); params.append(v.strip() if isinstance(v, str) else v)
        if "producto_faltante" in enviados:
            campos.append("enriquecido_ia = FALSE")     # lo corrigió una persona
        if "asignado_a" in enviados:
            if t["estado"] not in ESTADOS_ACTIVOS:
                raise HTTPException(status.HTTP_409_CONFLICT, "No se puede asignar un ticket cerrado o cancelado")
            if datos.asignado_a is None:
                if t["estado"] == "EN_PROGRESO":
                    raise HTTPException(status.HTTP_409_CONFLICT, "No se puede quitar el responsable de un ticket en progreso")
                campos += ["asignado_a = NULL", "estado = 'ABIERTO'"]
            else:
                campos.append("asignado_a = %s"); params.append(datos.asignado_a)
        nuevo = datos.estado if "estado" in enviados and datos.estado != t["estado"] else None
        if nuevo == "CERRADO":
            await _validar_cierre(conn, t, datos.comentario)
            pct = await _pct_cierre(conn, t["id"])
            if pct is not None:
                campos.append("porcentaje_vacio = %s"); params.append(pct)
        if nuevo == "CANCELADO" and not (datos.comentario or "").strip():
            raise HTTPException(422, "Indica el motivo de la cancelación")
        if nuevo:
            if nuevo in ("ASIGNADO", "EN_PROGRESO") and not (datos.asignado_a or t["asignado_a"]):
                raise HTTPException(status.HTTP_409_CONFLICT, "Primero asigna un reponedor")
            if nuevo == "ABIERTO":
                campos.append("asignado_a = NULL")
            campos.append("estado = %s"); params.append(nuevo)
        if campos:
            await conn.execute(f"UPDATE ticket SET {', '.join(campos)} WHERE id = %s", params + [t["id"]])
        if datos.comentario and datos.comentario.strip():
            prefijo = {"CERRADO": "Cierre: ", "CANCELADO": "Cancelado: "}.get(nuevo or "", "")
            await conn.execute("INSERT INTO comentario (ticket_id, usuario_id, texto) VALUES (%s, %s, %s)",
                               [t["id"], usuario.id, prefijo + datos.comentario.strip()])
        return await detalle(conn, numero, usuario)


# ---------------------------------------------------------------- comentarios

class NuevoComentario(BaseModel):
    texto: str = Field(min_length=1, max_length=2000)


@router.post("/{numero}/comentarios", status_code=201)
async def comentar(numero: str, datos: NuevoComentario, request: Request, usuario: Usuario = Depends(usuario_actual)):
    async with request.app.state.db.tx(usuario.id) as conn:
        t = await _ticket(conn, numero, usuario)
        if usuario.rol == REPONEDOR and usuario.id not in (t["asignado_a"], t["creado_por"]):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Solo puedes comentar tus tickets")
        return await uno(conn, """
            INSERT INTO comentario (ticket_id, usuario_id, texto) VALUES (%s, %s, %s)
            RETURNING id, usuario_id, texto, creado_en""", [t["id"], usuario.id, datos.texto.strip()])


# ---------------------------------------------------------------- cierre

@router.post("/{numero}/cierre", status_code=202)
async def foto_cierre(numero: str, request: Request, foto: UploadFile = File(...),
                      capturada_en: datetime | None = Form(None), usuario: Usuario = Depends(usuario_actual)):
    """Sube la foto de verificación. El worker la analiza; la app consulta
    GET /imagenes/{id} y muestra si quedó bajo el umbral."""
    async with request.app.state.db.tx() as conn:
        t = await _ticket(conn, numero, usuario)
    if not (t["asignado_a"] == usuario.id or usuario.rol in (SUPERVISOR, ADMIN)):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Solo el reponedor asignado puede cerrar")
    if t["estado"] not in ("ASIGNADO", "EN_PROGRESO"):
        raise HTTPException(status.HTTP_409_CONFLICT, "El ticket no está en curso")
    if not t["gondola_id"] and not t["categoria_id"]:
        raise HTTPException(status.HTTP_409_CONFLICT, "El ticket no tiene categoría: ciérralo con un comentario")
    async with request.app.state.db.tx() as conn:
        carpeta = await valor(conn, "SELECT carpeta_imagenes FROM recinto WHERE id = %s", [t["recinto_id"]])
    destino = Destino(t["recinto_id"], carpeta, t["categoria_id"], t["gondola_id"], t["gondola_codigo"] or "cierre")
    imagen_id = await registrar_foto_movil(request, usuario, foto, destino, capturada_en, ticket_cierre=t["id"])
    return {"imagen_id": imagen_id}


class Cierre(BaseModel):
    comentario: str | None = Field(None, max_length=2000)


async def _pct_cierre(conn, ticket_id: int):
    return await valor(conn, """
        SELECT p.porcentaje_vacio FROM ticket_imagen ti JOIN prediccion p ON p.imagen_id = ti.imagen_id
         WHERE ti.ticket_id = %s AND ti.tipo = 'CIERRE' ORDER BY ti.agregada_en DESC, p.creada_en DESC LIMIT 1""",
        [ticket_id])


async def _validar_cierre(conn, t: dict, comentario: str | None) -> bool:
    """Cierre verificado = última foto de CIERRE bajo el umbral. Sin eso,
    se exige un comentario (decisión del plan: se permite, pero queda explicado)."""
    ultima = await uno(conn, """
        SELECT i.estado, p.supera_umbral FROM ticket_imagen ti
          JOIN imagen i ON i.id = ti.imagen_id
          LEFT JOIN LATERAL (SELECT * FROM prediccion WHERE imagen_id = i.id ORDER BY creada_en DESC LIMIT 1) p ON TRUE
         WHERE ti.ticket_id = %s AND ti.tipo = 'CIERRE'
         ORDER BY ti.agregada_en DESC LIMIT 1""", [t["id"]])
    if ultima and ultima["estado"] in ("PENDIENTE", "PROCESANDO"):
        raise HTTPException(status.HTTP_409_CONFLICT, "La foto de verificación aún se está analizando")
    verificado = bool(ultima and ultima["supera_umbral"] is False)
    if not verificado and len((comentario or "").strip()) < 5:
        motivo = ("El vacío sigue sobre el umbral" if ultima and ultima["supera_umbral"]
                  else "No hay foto de verificación")
        raise HTTPException(422,
                            f"{motivo}: agrega un comentario de cierre para cerrar sin verificación")
    return verificado


@router.post("/{numero}/cerrar")
async def cerrar(numero: str, datos: Cierre, request: Request, usuario: Usuario = Depends(usuario_actual)):
    async with request.app.state.db.tx(usuario.id) as conn:
        t = await _ticket(conn, numero, usuario)
        await conn.execute("SELECT 1 FROM ticket WHERE id = %s FOR UPDATE", [t["id"]])
        if not (t["asignado_a"] == usuario.id or usuario.rol in (SUPERVISOR, ADMIN)):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Solo el reponedor asignado puede cerrar")
        if t["estado"] not in ("ASIGNADO", "EN_PROGRESO"):
            raise HTTPException(status.HTTP_409_CONFLICT, "El ticket no está en curso")
        await _validar_cierre(conn, t, datos.comentario)
        pct = await _pct_cierre(conn, t["id"])
        await conn.execute("UPDATE ticket SET estado = 'CERRADO', porcentaje_vacio = COALESCE(%s, porcentaje_vacio) "
                           "WHERE id = %s", [pct, t["id"]])
        if datos.comentario and datos.comentario.strip():
            await conn.execute("INSERT INTO comentario (ticket_id, usuario_id, texto) VALUES (%s, %s, %s)",
                               [t["id"], usuario.id, "Cierre: " + datos.comentario.strip()])
        return await detalle(conn, numero, usuario)
