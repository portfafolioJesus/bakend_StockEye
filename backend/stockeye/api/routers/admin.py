"""Administración: recintos, góndolas, cámaras, usuarios, modelos e integración de IA."""
from __future__ import annotations

import asyncio
import hashlib
import json
from typing import Literal

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from pydantic import BaseModel, Field

from ...core.config import ajustes
from ...core.db import todos, uno, valor
from ...core.fotos import slug
from ...core.seguridad import clave_temporal, hash_api_key, hash_clave, nueva_api_key
from ...ia.proveedor import PROVEEDORES, ErrorIA, crear_proveedor
from ...inferencia.registro import SQL_ACTIVAR, SQL_REGISTRAR, parametros_sql
from ..deps import ADMIN, SUPERVISOR, Usuario, exigir_recinto, requiere

router = APIRouter(prefix="/admin", tags=["administración"])
solo_admin = requiere(ADMIN)
gestion = requiere(ADMIN, SUPERVISOR)


def _actualizar(campos: dict, permitidos: set[str]) -> tuple[str, list]:
    sets, params = [], []
    for k, v in campos.items():
        if k in permitidos:
            sets.append(f"{k} = %s"); params.append(v)
    if not sets:
        raise HTTPException(422, "No hay cambios")
    return ", ".join(sets), params


# ---------------------------------------------------------------- recintos

class RecintoNuevo(BaseModel):
    codigo: str = Field(pattern=r"^[A-Z0-9-]{2,20}$")
    nombre: str = Field(min_length=2, max_length=120)
    direccion: str | None = None
    comuna: str | None = None
    umbral_vacio: float = Field(5.0, ge=0, le=100)


class RecintoCambio(BaseModel):
    nombre: str | None = Field(None, min_length=2, max_length=120)
    direccion: str | None = None
    comuna: str | None = None
    umbral_vacio: float | None = Field(None, ge=0, le=100)
    activo: bool | None = None


@router.get("/recintos")
async def recintos(request: Request, _: Usuario = Depends(solo_admin)):
    async with request.app.state.db.tx() as conn:
        return await todos(conn, """
            SELECT r.*,
                   (SELECT count(*) FROM usuario_recinto ur JOIN usuario u ON u.id = ur.usuario_id
                     WHERE ur.recinto_id = r.id AND u.rol = 'SUPERVISOR' AND u.activo) AS supervisores,
                   (SELECT count(*) FROM usuario_recinto ur JOIN usuario u ON u.id = ur.usuario_id
                     WHERE ur.recinto_id = r.id AND u.rol = 'REPONEDOR' AND u.activo) AS reponedores,
                   (SELECT count(*) FROM v_camara_estado c WHERE c.recinto_id = r.id AND c.activa AND c.tipo = 'IP') AS camaras,
                   (SELECT count(*) FROM v_camara_estado c WHERE c.recinto_id = r.id AND c.en_linea AND c.tipo = 'IP') AS camaras_en_linea
              FROM recinto r ORDER BY r.codigo""")


@router.post("/recintos", status_code=201)
async def crear_recinto(datos: RecintoNuevo, request: Request, u: Usuario = Depends(solo_admin)):
    async with request.app.state.db.tx(u.id) as conn:
        return await uno(conn, """
            INSERT INTO recinto (codigo, nombre, direccion, comuna, carpeta_imagenes, umbral_vacio)
            VALUES (%s, %s, %s, %s, %s, %s) RETURNING *""",
            [datos.codigo, datos.nombre, datos.direccion, datos.comuna, f"recintos/{datos.codigo}", datos.umbral_vacio])


@router.patch("/recintos/{recinto_id}")
async def editar_recinto(recinto_id: int, datos: RecintoCambio, request: Request, u: Usuario = Depends(solo_admin)):
    sets, params = _actualizar(datos.model_dump(exclude_unset=True), {"nombre", "direccion", "comuna", "umbral_vacio", "activo"})
    async with request.app.state.db.tx(u.id) as conn:
        fila = await uno(conn, f"UPDATE recinto SET {sets} WHERE id = %s RETURNING *", params + [recinto_id])
    if not fila:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Recinto no encontrado")
    return fila


# ---------------------------------------------------------------- góndolas

class GondolaNueva(BaseModel):
    """Punto fijo dentro de una categoría (ej. el lugar que mira una cámara)."""
    recinto_id: int
    categoria_id: int
    codigo: str | None = Field(None, max_length=20)
    pasillo: str | None = None
    descripcion: str | None = None


class GondolaCambio(BaseModel):
    codigo: str | None = Field(None, min_length=2, max_length=20)
    pasillo: str | None = None
    categoria_id: int | None = None
    descripcion: str | None = None
    activo: bool | None = None


@router.get("/gondolas")
async def gondolas(request: Request, recinto_id: int | None = None, u: Usuario = Depends(gestion)):
    if recinto_id:
        exigir_recinto(u, recinto_id)
    async with request.app.state.db.tx() as conn:
        return await todos(conn, """
            SELECT g.*, r.codigo AS recinto_codigo FROM gondola g JOIN recinto r ON r.id = g.recinto_id
             WHERE (%s::int IS NULL OR g.recinto_id = %s) AND (%s OR g.recinto_id = ANY(%s))
             ORDER BY r.codigo, g.codigo""", [recinto_id, recinto_id, u.es_admin, u.recintos])


@router.post("/gondolas", status_code=201)
async def crear_gondola(datos: GondolaNueva, request: Request, u: Usuario = Depends(solo_admin)):
    async with request.app.state.db.tx(u.id) as conn:
        cat = await uno(conn, "SELECT codigo FROM categoria WHERE id = %s", [datos.categoria_id])
        if not cat:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Categoría no encontrada")
        codigo = (datos.codigo or slug(f"{cat['codigo']}-{datos.descripcion or datos.pasillo or 'PUNTO'}", 20)).upper()
        return await uno(conn, """INSERT INTO gondola (recinto_id, codigo, pasillo, categoria_id, descripcion)
                                  VALUES (%s, %s, %s, %s, %s) RETURNING *""",
                         [datos.recinto_id, codigo, datos.pasillo, datos.categoria_id, datos.descripcion])


@router.patch("/gondolas/{gondola_id}")
async def editar_gondola(gondola_id: int, datos: GondolaCambio, request: Request, u: Usuario = Depends(solo_admin)):
    sets, params = _actualizar(datos.model_dump(exclude_unset=True), {"codigo", "pasillo", "categoria_id", "descripcion", "activo"})
    async with request.app.state.db.tx(u.id) as conn:
        return await uno(conn, f"UPDATE gondola SET {sets} WHERE id = %s RETURNING *", params + [gondola_id])


# ---------------------------------------------------------------- cámaras

class CamaraNueva(BaseModel):
    recinto_id: int
    gondola_id: int | None = None
    codigo: str = Field(pattern=r"^[A-Z0-9-]{3,30}$")
    nombre: str | None = None
    url_stream: str | None = Field(None, description="Sin usuario ni clave: esos viven solo en el capturador")
    intervalo_captura_seg: int = Field(300, ge=30)
    roi: list[list[float]] | None = None


class CamaraCambio(BaseModel):
    gondola_id: int | None = None
    nombre: str | None = None
    url_stream: str | None = None
    intervalo_captura_seg: int | None = Field(None, ge=30)
    activa: bool | None = None
    roi: list[list[float]] | None = None


def _sin_credenciales(url: str | None) -> str | None:
    if url and "@" in url.split("//", 1)[-1].split("/", 1)[0]:
        raise HTTPException(422,
                            "No guardes usuario/clave en la URL: van solo en el capturador del recinto")
    return url


@router.get("/camaras")
async def camaras(request: Request, recinto_id: int | None = None, u: Usuario = Depends(gestion)):
    async with request.app.state.db.tx() as conn:
        return await todos(conn, """
            SELECT * FROM v_camara_estado
             WHERE tipo = 'IP' AND (%s::int IS NULL OR recinto_id = %s) AND (%s OR recinto_id = ANY(%s))
             ORDER BY en_linea, recinto_codigo, codigo""", [recinto_id, recinto_id, u.es_admin, u.recintos])


@router.post("/camaras", status_code=201)
async def crear_camara(datos: CamaraNueva, request: Request, u: Usuario = Depends(solo_admin)):
    """Devuelve la API key UNA sola vez; en la BD queda solo su hash."""
    clave = nueva_api_key(datos.codigo)
    async with request.app.state.db.tx(u.id) as conn:
        cam = await uno(conn, """
            INSERT INTO camara (recinto_id, gondola_id, codigo, nombre, url_stream, api_key_hash,
                                intervalo_captura_seg, roi)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING id, codigo""",
            [datos.recinto_id, datos.gondola_id, datos.codigo, datos.nombre or f"Cámara {datos.codigo}",
             _sin_credenciales(datos.url_stream), hash_api_key(clave), datos.intervalo_captura_seg,
             json.dumps(datos.roi) if datos.roi else None])
    return {**cam, "api_key": clave, "aviso": "Guarda esta API key ahora: no se volverá a mostrar."}


@router.patch("/camaras/{camara_id}")
async def editar_camara(camara_id: int, datos: CamaraCambio, request: Request, u: Usuario = Depends(solo_admin)):
    cambios = datos.model_dump(exclude_unset=True)
    if "url_stream" in cambios:
        _sin_credenciales(cambios["url_stream"])
    if "roi" in cambios:
        cambios["roi"] = json.dumps(cambios["roi"]) if cambios["roi"] else None
    sets, params = _actualizar(cambios, {"gondola_id", "nombre", "url_stream", "intervalo_captura_seg", "activa", "roi"})
    async with request.app.state.db.tx(u.id) as conn:
        await conn.execute(f"UPDATE camara SET {sets} WHERE id = %s", params + [camara_id])
        return await uno(conn, "SELECT * FROM v_camara_estado WHERE id = %s", [camara_id])


@router.post("/camaras/{camara_id}/clave")
async def regenerar_clave(camara_id: int, request: Request, u: Usuario = Depends(solo_admin)):
    async with request.app.state.db.tx(u.id) as conn:
        codigo = await valor(conn, "SELECT codigo FROM camara WHERE id = %s", [camara_id])
        if not codigo:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Cámara no encontrada")
        clave = nueva_api_key(codigo)
        await conn.execute("UPDATE camara SET api_key_hash = %s WHERE id = %s", [hash_api_key(clave), camara_id])
    return {"codigo": codigo, "api_key": clave, "aviso": "La clave anterior dejó de funcionar."}


@router.get("/camaras/{camara_id}/diagnostico")
async def diagnosticar(camara_id: int, request: Request, u: Usuario = Depends(gestion)):
    async with request.app.state.db.tx() as conn:
        c = await uno(conn, "SELECT * FROM v_camara_estado WHERE id = %s", [camara_id])
        if not c:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Cámara no encontrada")
        exigir_recinto(u, c["recinto_id"])
        ultimas = await todos(conn, """
            SELECT i.id, i.capturada_en, i.recibida_en, i.estado, i.error_detalle, p.porcentaje_vacio
              FROM imagen i LEFT JOIN prediccion p ON p.imagen_id = i.id
             WHERE i.camara_id = %s ORDER BY i.recibida_en DESC LIMIT 10""", [camara_id])
        minutos = await valor(conn, "SELECT EXTRACT(EPOCH FROM now() - %s::timestamptz) / 60", [c["ultima_captura"]]) \
            if c["ultima_captura"] else None
    pasos = []
    if not c["activa"]:
        pasos.append("La cámara está desactivada en el sistema.")
    if c["ultima_captura"] is None:
        pasos.append("Nunca envió fotos: revisa que el capturador del recinto tenga su API key y la URL correcta.")
    elif not c["en_linea"]:
        pasos.append(f"Sin fotos hace {round(minutos or 0)} min (debería enviar cada {c['intervalo_captura_seg'] // 60} min).")
        pasos.append("Verifica que el capturador del recinto esté encendido y con internet (journalctl -u stockeye-capturador).")
        pasos.append("Prueba la cámara en el recinto: ffmpeg -rtsp_transport tcp -i \"rtsp://...\" -frames:v 1 prueba.jpg")
    if c["ultimo_error"]:
        pasos.append(f"Último error del capturador: {c['ultimo_error']}")
    errores = [i for i in ultimas if i["estado"] == "ERROR"]
    if errores:
        pasos.append(f"{len(errores)} de las últimas fotos fallaron en el análisis: {errores[0]['error_detalle']}")
    return {"camara": c, "minutos_sin_foto": minutos, "ultimas_imagenes": ultimas,
            "pasos": pasos or ["La cámara funciona con normalidad."]}


# ---------------------------------------------------------------- usuarios

Rol = Literal["ADMINISTRADOR", "SUPERVISOR", "REPONEDOR"]


class UsuarioNuevo(BaseModel):
    nombre: str = Field(min_length=1, max_length=80)
    apellido: str = Field(min_length=1, max_length=80)
    email: str = Field(pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    rol: Rol
    recintos: list[int] = []
    rut: str | None = None
    telefono: str | None = None


class UsuarioCambio(BaseModel):
    nombre: str | None = None
    apellido: str | None = None
    rol: Rol | None = None
    activo: bool | None = None
    telefono: str | None = None
    recintos: list[int] | None = None


@router.get("/usuarios")
async def usuarios(request: Request, _: Usuario = Depends(solo_admin)):
    async with request.app.state.db.tx() as conn:
        return await todos(conn, """
            SELECT u.id, u.rut, u.nombre, u.apellido, u.email, u.telefono, u.rol, u.activo, u.ultimo_acceso,
                   u.ultimo_acceso_origen, u.debe_cambiar_clave,
                   COALESCE(array_agg(r.codigo ORDER BY r.codigo) FILTER (WHERE r.id IS NOT NULL), '{}') AS recintos,
                   COALESCE(array_agg(r.id ORDER BY r.codigo) FILTER (WHERE r.id IS NOT NULL), '{}') AS recinto_ids
              FROM usuario u
              LEFT JOIN usuario_recinto ur ON ur.usuario_id = u.id
              LEFT JOIN recinto r ON r.id = ur.recinto_id
             GROUP BY u.id ORDER BY u.activo DESC, u.rol, u.nombre""")


@router.post("/usuarios", status_code=201)
async def invitar(datos: UsuarioNuevo, request: Request, u: Usuario = Depends(solo_admin)):
    """Crea el usuario con una clave temporal (se muestra una vez) que debe cambiar al ingresar."""
    if datos.rol != "ADMINISTRADOR" and not datos.recintos:
        raise HTTPException(422, "Asigna al menos un recinto")
    temporal = clave_temporal()
    async with request.app.state.db.tx(u.id) as conn:
        nuevo = await uno(conn, """
            INSERT INTO usuario (rut, nombre, apellido, email, telefono, password_hash, rol, debe_cambiar_clave)
            VALUES (%s, %s, %s, %s, %s, %s, %s, TRUE) RETURNING id, nombre, apellido, email, rol""",
            [datos.rut, datos.nombre, datos.apellido, datos.email.lower(), datos.telefono, hash_clave(temporal), datos.rol])
        for rid in set(datos.recintos):
            await conn.execute("INSERT INTO usuario_recinto (usuario_id, recinto_id) VALUES (%s, %s)", [nuevo["id"], rid])
    return {**nuevo, "clave_temporal": temporal}


@router.patch("/usuarios/{usuario_id}")
async def editar_usuario(usuario_id: int, datos: UsuarioCambio, request: Request, u: Usuario = Depends(solo_admin)):
    cambios = datos.model_dump(exclude_unset=True)
    recintos = cambios.pop("recintos", None)
    if usuario_id == u.id and (cambios.get("activo") is False or cambios.get("rol") not in (None, ADMIN)):
        raise HTTPException(status.HTTP_409_CONFLICT, "No puedes quitarte el rol ni desactivarte a ti mismo")
    async with request.app.state.db.tx(u.id) as conn:
        if cambios:
            sets, params = _actualizar(cambios, {"nombre", "apellido", "rol", "activo", "telefono"})
            await conn.execute(f"UPDATE usuario SET {sets} WHERE id = %s", params + [usuario_id])
        if recintos is not None:
            await conn.execute("DELETE FROM usuario_recinto WHERE usuario_id = %s AND NOT (recinto_id = ANY(%s))",
                               [usuario_id, recintos])
            for rid in set(recintos):
                await conn.execute("""INSERT INTO usuario_recinto (usuario_id, recinto_id) VALUES (%s, %s)
                                      ON CONFLICT DO NOTHING""", [usuario_id, rid])
        return await uno(conn, "SELECT id, nombre, apellido, email, rol, activo FROM usuario WHERE id = %s", [usuario_id])


@router.post("/usuarios/{usuario_id}/clave")
async def restablecer_clave(usuario_id: int, request: Request, u: Usuario = Depends(solo_admin)):
    temporal = clave_temporal()
    async with request.app.state.db.tx(u.id) as conn:
        fila = await uno(conn, """UPDATE usuario SET password_hash = %s, debe_cambiar_clave = TRUE WHERE id = %s
                                  RETURNING email""", [hash_clave(temporal), usuario_id])
    if not fila:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Usuario no encontrado")
    return {"email": fila["email"], "clave_temporal": temporal}


# ---------------------------------------------------------------- modelos

@router.get("/modelos")
async def modelos(request: Request, _: Usuario = Depends(solo_admin)):
    async with request.app.state.db.tx() as conn:
        filas = await todos(conn, """
            SELECT m.id, m.nombre, m.version, m.familia, m.ruta_pesos, m.sha256_pesos, m.umbral_confianza, m.clases,
                   m.map50, m.metricas, m.parametros, m.activo, m.cargado_en, m.activado_en,
                   u.nombre || ' ' || u.apellido AS activado_por_nombre,
                   (SELECT count(*) FROM prediccion p WHERE p.modelo_id = m.id) AS predicciones,
                   (SELECT round(avg(tiempo_inferencia_ms)) FROM prediccion p
                     WHERE p.modelo_id = m.id AND p.creada_en > now() - interval '1 day') AS inferencia_ms_promedio
              FROM modelo_ia m LEFT JOIN usuario u ON u.id = m.activado_por
             ORDER BY m.activo DESC, m.cargado_en DESC""")
    for f in filas:
        f["archivo_presente"] = (ajustes().modelos_dir / f["ruta_pesos"].split("/")[-1]).is_file()
    return filas


@router.post("/modelos", status_code=201)
async def subir_modelo(request: Request, archivo: UploadFile = File(..., description=".onnx exportado"),
                       manifiesto: UploadFile = File(..., description=".json del empaquetador"),
                       u: Usuario = Depends(solo_admin)):
    """Sube un modelo YA exportado a ONNX con herramientas/empaquetar_modelo.py.
    (Convertir un .pt requiere PyTorch y no cabe en el servidor de 4 GB.)"""
    try:
        m = json.loads(await manifiesto.read())
    except json.JSONDecodeError:
        raise HTTPException(422, "El manifiesto no es JSON válido")
    nombre_archivo = f"{m.get('nombre', 'modelo')}-{m.get('version', 'v')}.onnx".replace("/", "_")
    destino = ajustes().modelos_dir / nombre_archivo
    h = hashlib.sha256()
    tmp = destino.with_suffix(".subiendo")
    destino.parent.mkdir(parents=True, exist_ok=True)
    with tmp.open("wb") as f:
        while bloque := await archivo.read(1 << 20):
            h.update(bloque); f.write(bloque)
    if m.get("sha256") and m["sha256"] != h.hexdigest():
        tmp.unlink(missing_ok=True)
        raise HTTPException(422, "El sha256 del .onnx no coincide con el manifiesto")
    m["sha256"] = h.hexdigest()
    try:
        params = parametros_sql({**m, "archivo": nombre_archivo}, f"modelos/{nombre_archivo}")
    except ValueError as e:
        tmp.unlink(missing_ok=True)
        raise HTTPException(422, str(e))
    tmp.replace(destino)
    async with request.app.state.db.tx(u.id) as conn:
        modelo_id = await valor(conn, SQL_REGISTRAR, params)
    return {"id": modelo_id, "archivo": nombre_archivo, "sha256": m["sha256"]}


@router.post("/modelos/{modelo_id}/activar")
async def activar_modelo(modelo_id: int, request: Request, u: Usuario = Depends(solo_admin)):
    """También sirve para "Volver a esta" versión. Los workers recargan solos (NOTIFY)."""
    async with request.app.state.db.tx(u.id) as conn:
        ruta = await valor(conn, "SELECT ruta_pesos FROM modelo_ia WHERE id = %s", [modelo_id])
        if not ruta:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Modelo no encontrado")
        if not (ajustes().modelos_dir / ruta.split("/")[-1]).is_file():
            raise HTTPException(status.HTTP_409_CONFLICT, f"El archivo {ruta} no está en el servidor")
        return await uno(conn, SQL_ACTIVAR, {"id": modelo_id, "usuario": u.id})


class ModeloCambio(BaseModel):
    umbral_confianza: float = Field(ge=0.05, le=0.95)


@router.patch("/modelos/{modelo_id}")
async def editar_modelo(modelo_id: int, datos: ModeloCambio, request: Request, u: Usuario = Depends(solo_admin)):
    async with request.app.state.db.tx(u.id) as conn:
        return await uno(conn, "UPDATE modelo_ia SET umbral_confianza = %s WHERE id = %s RETURNING id, umbral_confianza",
                         [datos.umbral_confianza, modelo_id])


# ---------------------------------------------------------------- integración de IA

class IACambio(BaseModel):
    activo: bool | None = None
    proveedor: str | None = None
    modelo: str | None = Field(None, min_length=2, max_length=120)
    recortar_a_gondola: bool | None = None


def _clave_configurada(proveedor: str) -> bool:
    a = ajustes()
    return bool({"groq": a.groq_api_key, "openai": a.openai_api_key}.get(proveedor))


@router.get("/ia")
async def ia(request: Request, _: Usuario = Depends(solo_admin)):
    from ...ia import openai_compatible  # noqa: F401  (registra proveedores)
    async with request.app.state.db.tx() as conn:
        c = await uno(conn, "SELECT * FROM configuracion_ia")
        uso = await uno(conn, """SELECT count(*) AS analisis, count(*) FILTER (WHERE NOT exitoso) AS fallidos,
                                        round(avg(latencia_ms)) AS latencia_ms, sum(tokens_entrada) AS tokens_entrada,
                                        sum(tokens_salida) AS tokens_salida
                                   FROM analisis_ia WHERE creado_en > now() - interval '7 days'""")
    return {**c, "api_key_configurada": _clave_configurada(c["proveedor"]),
            "proveedores": sorted(PROVEEDORES), "uso_7_dias": uso,
            "modelo_forzado_por_entorno": ajustes().ia_modelo}


@router.patch("/ia")
async def editar_ia(datos: IACambio, request: Request, u: Usuario = Depends(solo_admin)):
    from ...ia import openai_compatible  # noqa: F401
    cambios = datos.model_dump(exclude_unset=True)
    if "proveedor" in cambios and cambios["proveedor"] not in PROVEEDORES:
        raise HTTPException(422, f"Proveedores: {', '.join(sorted(PROVEEDORES))}")
    sets, params = _actualizar(cambios, {"activo", "proveedor", "modelo", "recortar_a_gondola"})
    async with request.app.state.db.tx(u.id) as conn:
        return await uno(conn, f"""UPDATE configuracion_ia SET {sets}, actualizado_en = now(), actualizado_por = %s
                                   RETURNING *""", params + [u.id])


@router.post("/ia/probar")
async def probar_ia(request: Request, _: Usuario = Depends(solo_admin)):
    async with request.app.state.db.tx() as conn:
        c = await uno(conn, "SELECT proveedor, modelo FROM configuracion_ia")
    try:
        proveedor = crear_proveedor(c["proveedor"], c["modelo"], ajustes())
    except ErrorIA as e:
        return {"ok": False, "detalle": str(e)}
    return await asyncio.to_thread(proveedor.probar)


# ---------------------------------------------------------------- cola (observabilidad)

@router.get("/cola")
async def cola(request: Request, _: Usuario = Depends(solo_admin)):
    """Estado de la cola de inferencia por recinto: sirve para ver si hay cuello de botella."""
    async with request.app.state.db.tx() as conn:
        por_recinto = await todos(conn, """
            SELECT r.codigo AS recinto,
                   count(*) FILTER (WHERE i.estado = 'PENDIENTE')  AS pendientes,
                   count(*) FILTER (WHERE i.estado = 'PROCESANDO') AS procesando,
                   count(*) FILTER (WHERE i.estado = 'ERROR' AND i.recibida_en > now() - interval '1 day') AS errores_24h,
                   round(percentile_cont(0.95) WITHIN GROUP (ORDER BY EXTRACT(EPOCH FROM i.procesada_en - i.recibida_en))
                         FILTER (WHERE i.procesada_en > now() - interval '1 hour')::numeric, 2) AS p95_espera_s,
                   min(i.recibida_en) FILTER (WHERE i.estado = 'PENDIENTE') AS pendiente_mas_antigua
              FROM recinto r LEFT JOIN imagen i ON i.recinto_id = r.id
             GROUP BY r.codigo ORDER BY r.codigo""")
        workers = await todos(conn, """
            SELECT tomada_por AS worker, count(*) AS imagenes_ultima_hora, max(procesada_en) AS ultima
              FROM imagen WHERE procesada_en > now() - interval '1 hour' AND tomada_por IS NOT NULL
             GROUP BY tomada_por ORDER BY 1""")
        tareas = await todos(conn, "SELECT tipo, estado, count(*) AS n FROM tarea GROUP BY 1, 2 ORDER BY 1, 2")
    return {"recintos": por_recinto, "workers": workers, "tareas": tareas}
