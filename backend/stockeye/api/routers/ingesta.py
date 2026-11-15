"""Ingesta desde las cámaras (capturador del recinto). Autenticación por X-API-Key."""
from datetime import datetime

from fastapi import APIRouter, File, Form, Header, HTTPException, Request, UploadFile, status
from pydantic import BaseModel, Field

from ...core.db import uno
from ...core.seguridad import hash_api_key
from ..fotos import guardar_foto, leer_foto

router = APIRouter(prefix="/ingesta", tags=["ingesta (cámaras)"])


async def camara_por_clave(conn, api_key: str | None) -> dict:
    if not api_key:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Falta X-API-Key")
    cam = await uno(conn, """
        SELECT c.id, c.codigo, c.recinto_id, c.gondola_id, c.activa, r.carpeta_imagenes
          FROM camara c JOIN recinto r ON r.id = c.recinto_id
         WHERE c.api_key_hash = %s""", [hash_api_key(api_key)])
    if not cam or not cam["activa"]:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "API key inválida o cámara desactivada")
    return cam


@router.post("", status_code=202)
async def ingesta(request: Request, foto: UploadFile = File(...), camara: str | None = Form(None),
                  capturada_en: datetime | None = Form(None), x_api_key: str | None = Header(None)):
    """Recibe una foto de cámara, la guarda en la carpeta del recinto y la deja en cola.
    Responde de inmediato (202): la inferencia la hace el worker."""
    base = request.app.state.db
    async with base.tx() as conn:
        cam = await camara_por_clave(conn, x_api_key)
    if camara and camara != cam["codigo"]:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "La API key no corresponde a esa cámara")
    f = await leer_foto(foto)
    ruta = guardar_foto(f, cam["carpeta_imagenes"], cam["codigo"], capturada_en)
    async with base.tx() as conn:
        img = await uno(conn, """
            INSERT INTO imagen (recinto_id, gondola_id, camara_id, origen, ruta_archivo, sha256,
                                ancho_px, alto_px, capturada_en)
            VALUES (%s, %s, %s, 'CAMARA', %s, %s, %s, %s, COALESCE(%s, now()))
            RETURNING id""",
            [cam["recinto_id"], cam["gondola_id"], cam["id"], ruta, f.sha256, f.ancho, f.alto, capturada_en])
        await conn.execute("""UPDATE camara SET ultima_captura = now(), ultimo_error = NULL, ultimo_error_en = NULL
                               WHERE id = %s""", [cam["id"]])
    return {"imagen_id": img["id"], "ruta": ruta}


class ErrorCaptura(BaseModel):
    detalle: str = Field(min_length=1, max_length=1000)


@router.post("/error", status_code=204)
async def reportar_error(datos: ErrorCaptura, request: Request, x_api_key: str | None = Header(None)):
    """El capturador avisa que no pudo leer la cámara (lo muestra "Diagnosticar")."""
    async with request.app.state.db.tx() as conn:
        cam = await camara_por_clave(conn, x_api_key)
        await conn.execute("UPDATE camara SET ultimo_error = %s, ultimo_error_en = now() WHERE id = %s",
                           [datos.detalle, cam["id"]])
