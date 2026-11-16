"""Caracterización automática y revisión manual, limitada al recinto del Supervisor."""
from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from ...core.db import todos, uno, valor
from ...core.seguridad import url_firmada
from ..deps import ADMIN, SUPERVISOR, Usuario, exigir_recinto, requiere

router=APIRouter(prefix="/caracterizaciones", tags=["caracterizaciones"])
PENDIENTES=("PENDIENTE","PROCESANDO","REVISION")
ESTADOS={"NO_REQUERIDA","PENDIENTE","PROCESANDO","AUTOMATICA","MANUAL","REVISION"}
CAMPOS="""
SELECT i.id,i.recinto_id,i.categoria_id,cat.nombre AS categoria,i.estado_caracterizacion,
       i.producto_caracterizado,i.version_caracterizacion,i.estado,i.recibida_en,
       i.ruta_archivo,i.caracterizacion_detalle ->> 'nombre_original' AS nombre_original,
       p.porcentaje_vacio,t.numero AS ticket_numero
  FROM imagen i LEFT JOIN categoria cat ON cat.id=i.categoria_id
  LEFT JOIN LATERAL (SELECT porcentaje_vacio FROM prediccion WHERE imagen_id=i.id
                     ORDER BY creada_en DESC,id DESC LIMIT 1) p ON TRUE
  LEFT JOIN LATERAL (SELECT t.numero FROM ticket_imagen ti JOIN ticket t ON t.id=ti.ticket_id
                     WHERE ti.imagen_id=i.id ORDER BY ti.agregada_en DESC LIMIT 1) t ON TRUE
"""

def presentar(fila):
    fila["url_original"]=url_firmada(fila.pop("ruta_archivo"))
    return fila

@router.get("")
async def listar(request:Request,recinto_id:int,estado:str="",limite:int=Query(100,ge=1,le=200),
                 offset:int=Query(0,ge=0),usuario:Usuario=Depends(requiere(ADMIN,SUPERVISOR))):
    exigir_recinto(usuario,recinto_id)
    if estado and estado not in ESTADOS and estado!="pendientes":
        raise HTTPException(422,"Estado de caracterización inválido")
    filtros=" WHERE i.recinto_id=%s AND (i.sha256 IS NOT NULL OR i.estado_caracterizacion<>'NO_REQUERIDA')"
    params=[recinto_id]
    if estado=="pendientes":
        filtros+=" AND i.estado_caracterizacion=ANY(%s)";params.append(list(PENDIENTES))
    elif estado:
        filtros+=" AND i.estado_caracterizacion=%s";params.append(estado)
    async with request.app.state.db.tx() as conn:
        filas=await todos(conn,CAMPOS+filtros+" ORDER BY i.recibida_en DESC,i.id DESC LIMIT %s OFFSET %s",params+[limite,offset])
        total=await valor(conn,"SELECT count(*) FROM imagen i"+filtros,params)
        pendientes=await valor(conn,"SELECT count(*) FROM imagen WHERE recinto_id=%s AND estado_caracterizacion=ANY(%s)",[recinto_id,list(PENDIENTES)])
        categorias=await todos(conn,"SELECT id,codigo,nombre FROM categoria WHERE activo ORDER BY orden,nombre")
        incidencias=await todos(conn,"""SELECT a.id,a.motivo,a.mensaje,a.reintentar_en,a.creada_en,
            (SELECT count(*) FROM imagen WHERE recinto_id=%s AND estado_caracterizacion=ANY(%s)) AS pendientes
            FROM incidencia_ia a JOIN incidencia_ia_recinto ar ON ar.incidencia_id=a.id
            WHERE ar.recinto_id=%s AND a.resuelta_en IS NULL ORDER BY a.creada_en DESC""",[recinto_id,list(PENDIENTES),recinto_id])
    return {"imagenes":[presentar(f) for f in filas],"total":total,"pendientes":pendientes,
            "categorias":categorias,"incidencias":incidencias}

class CaracterizacionManual(BaseModel):
    categoria_id:int=Field(gt=0)
    producto:str|None=Field(None,max_length=150)
    version:int=Field(ge=0)

@router.patch("/{imagen_id}")
async def caracterizar(imagen_id:int,datos:CaracterizacionManual,request:Request,
                       usuario:Usuario=Depends(requiere(ADMIN,SUPERVISOR))):
    async with request.app.state.db.tx(usuario.id) as conn:
        visible=await uno(conn,"SELECT recinto_id FROM imagen WHERE id=%s",[imagen_id])
        if not visible:raise HTTPException(404,"Imagen no encontrada")
        exigir_recinto(usuario,visible["recinto_id"])
        await conn.execute("SELECT pg_advisory_xact_lock(727006,%s)",[visible["recinto_id"]])
        fila=await uno(conn,"SELECT id,version_caracterizacion FROM imagen WHERE id=%s FOR UPDATE",[imagen_id])
        if fila["version_caracterizacion"]!=datos.version:
            raise HTTPException(409,"La imagen cambió. Actualiza la vista antes de guardar.")
        if not await valor(conn,"SELECT id FROM categoria WHERE id=%s AND activo",[datos.categoria_id]):
            raise HTTPException(422,"Selecciona una categoría activa")
        await conn.execute("""UPDATE imagen SET categoria_id=%s,producto_caracterizado=%s,
            estado_caracterizacion='MANUAL',caracterizada_por=%s,caracterizada_en=now(),
            version_caracterizacion=version_caracterizacion+1,
            caracterizacion_detalle=caracterizacion_detalle || jsonb_build_object('origen','MANUAL')
            WHERE id=%s""",[datos.categoria_id,(datos.producto or '').strip() or None,usuario.id,imagen_id])
        await conn.execute("""UPDATE tarea SET estado='HECHA',terminada_en=now(),error=NULL
            WHERE tipo='CLASIFICAR_IMAGEN' AND (payload->>'imagen_id')::bigint=%s
            AND estado IN ('PENDIENTE','PROCESANDO')""",[imagen_id])
        await conn.execute("SELECT fn_aplicar_caracterizacion(%s)",[imagen_id])
        await conn.execute("SELECT pg_notify('imagen_procesada',json_build_object('imagen_id',%s,'recinto_id',%s)::text)",[imagen_id,visible['recinto_id']])
        actual=await uno(conn,CAMPOS+" WHERE i.id=%s",[imagen_id])
    return presentar(actual)
