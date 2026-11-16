"""Fotos desde la app del reponedor y desde el panel. La inferencia es
asíncrona: se sube (202) y se consulta GET /imagenes/{id} hasta que esté PROCESADA.

Cada foto se ubica por CATEGORÍA (Lácteos, Bebidas…) y, opcionalmente, por un
PUNTO FIJO dentro de ella (gondola_id). Basta con indicar uno de los dos."""
from dataclasses import dataclass
from datetime import datetime

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status

from ...core.db import uno
from ...core.fotos import SQL_IMAGEN_CARGA, SQL_IMAGEN_CARGA_CATEGORIA
from ..consultas import detalle_imagen
from ..deps import ADMIN, REPONEDOR, SUPERVISOR, Usuario, exigir_recinto, requiere, usuario_actual
from ..fotos import guardar_foto, leer_foto

router = APIRouter(prefix="/imagenes", tags=["imágenes"])


@dataclass
class Destino:
    """Dónde va la foto: recinto + categoría y, si hay, punto fijo (góndola)."""
    recinto_id: int
    carpeta_imagenes: str
    categoria_id: int | None
    gondola_id: int | None
    prefijo: str


async def resolver_destino(conn, usuario: Usuario, *, gondola_id: int | None = None, categoria_id: int | None = None,
                           recinto_id: int | None = None) -> Destino:
    if gondola_id:
        g = await uno(conn, """SELECT g.id, g.codigo, g.recinto_id, g.categoria_id, r.carpeta_imagenes
                                 FROM gondola g JOIN recinto r ON r.id = g.recinto_id
                                WHERE g.id = %s AND g.activo""", [gondola_id])
        if not g:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Punto fijo (góndola) no encontrado")
        exigir_recinto(usuario, g["recinto_id"])
        return Destino(g["recinto_id"], g["carpeta_imagenes"], g["categoria_id"], g["id"], g["codigo"])
    if not categoria_id:
        raise HTTPException(422, "Indica la categoría (o un punto fijo) de la foto")
    if recinto_id is None:
        if len(usuario.recintos) != 1:
            raise HTTPException(422, "Indica el recinto")
        recinto_id = usuario.recintos[0]
    exigir_recinto(usuario, recinto_id)
    fila = await uno(conn, """SELECT r.carpeta_imagenes, c.codigo FROM recinto r, categoria c
                               WHERE r.id = %s AND c.id = %s AND c.activo""", [recinto_id, categoria_id])
    if not fila:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Recinto o categoría no encontrados")
    return Destino(recinto_id, fila["carpeta_imagenes"], categoria_id, None, fila["codigo"])


async def registrar_foto_movil(request: Request, usuario: Usuario, foto: UploadFile, destino: Destino,
                               capturada_en: datetime | None, ticket_cierre: int | None = None) -> int:
    """Guarda la foto y crea la imagen PENDIENTE. Si es foto de cierre, la
    asocia al ticket en la MISMA transacción (el worker la ve ya como CIERRE)."""
    f = await leer_foto(foto)
    ruta = guardar_foto(f, destino.carpeta_imagenes, f"movil_u{usuario.id}_{destino.prefijo}", capturada_en)
    async with request.app.state.db.tx(usuario.id) as conn:
        img = await uno(conn, """
            INSERT INTO imagen (recinto_id, gondola_id, categoria_id, subida_por, origen, ruta_archivo, sha256,
                                ancho_px, alto_px, capturada_en)
            VALUES (%s, %s, %s, %s, 'MOVIL', %s, %s, %s, %s, COALESCE(%s, now()))
            RETURNING id""", [destino.recinto_id, destino.gondola_id, destino.categoria_id, usuario.id, ruta,
                              f.sha256, f.ancho, f.alto, capturada_en])
        if ticket_cierre:
            await conn.execute("INSERT INTO ticket_imagen (ticket_id, imagen_id, tipo) VALUES (%s, %s, 'CIERRE')",
                               [ticket_cierre, img["id"]])
    return img["id"]


@router.post("", status_code=202)
async def subir(request: Request, foto: UploadFile = File(...), categoria_id: int | None = Form(None),
                gondola_id: int | None = Form(None), recinto_id: int | None = Form(None),
                capturada_en: datetime | None = Form(None),
                usuario: Usuario = Depends(requiere(REPONEDOR, SUPERVISOR))):
    """Foto nueva desde la app (categoría y, opcional, punto fijo). El worker la
    analiza; el ticket se crea solo si el reponedor lo confirma (POST /tickets con imagen_id)."""
    async with request.app.state.db.tx() as conn:
        destino = await resolver_destino(conn, usuario, gondola_id=gondola_id, categoria_id=categoria_id,
                                         recinto_id=recinto_id)
    return {"imagen_id": await registrar_foto_movil(request, usuario, foto, destino, capturada_en)}


@router.post("/carga", status_code=202)
async def cargar(request: Request, fotos: list[UploadFile] = File(...), categoria_id: int | None = Form(None),
                 gondola_id: int | None = Form(None), recinto_id: int | None = Form(None),
                 usuario: Usuario = Depends(requiere(SUPERVISOR, ADMIN))):
    """Sube fotos reales desde el panel. Solo con categoría: cada foto sobre el
    umbral abre su propio ticket. Con punto fijo: como una cámara (ticket o SEGUIMIENTO)."""
    if len(fotos) > 50:
        raise HTTPException(422, "Máximo 50 fotos por carga")
    base = request.app.state.db
    async with base.tx() as conn:
        d = await resolver_destino(conn, usuario, gondola_id=gondola_id, categoria_id=categoria_id, recinto_id=recinto_id)
    resultados = []
    for archivo in fotos:
        try:
            f = await leer_foto(archivo)
        except HTTPException as e:
            resultados.append({"archivo": archivo.filename, "error": e.detail})
            continue
        ruta = guardar_foto(f, d.carpeta_imagenes, f"{d.prefijo}_panel", None)
        async with base.tx(usuario.id) as conn:
            if d.gondola_id:
                fila = await uno(conn, SQL_IMAGEN_CARGA, [ruta, f.sha256, f.ancho, f.alto, None, d.gondola_id])
            else:
                fila = await uno(conn, SQL_IMAGEN_CARGA_CATEGORIA, [d.recinto_id, d.recinto_id, d.categoria_id, ruta,
                                                                    f.sha256, f.ancho, f.alto, None])
            await conn.execute("UPDATE camara SET ultima_captura = now() WHERE id = %s", [fila["camara_id"]])
        resultados.append({"archivo": archivo.filename, "imagen_id": fila["id"]})
    return {"destino": d.prefijo, "resultados": resultados}


@router.get("/{imagen_id}")
async def obtener(imagen_id: int, request: Request, usuario: Usuario = Depends(usuario_actual)):
    async with request.app.state.db.tx() as conn:
        d = await detalle_imagen(conn, imagen_id)
    if not d:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Imagen no encontrada")
    exigir_recinto(usuario, d["recinto_id"])
    return d
