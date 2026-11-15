"""Entrega de fotos con URL firmada (la API las firma al listarlas)."""
from fastapi import APIRouter, HTTPException, status
from fastapi.responses import FileResponse

from ...core.almacenamiento import almacenamiento
from ...core.seguridad import verificar_firma

router = APIRouter(tags=["archivos"])


@router.get("/archivos/{ruta:path}")
async def archivo(ruta: str, exp: int, firma: str):
    if not verificar_firma(ruta, exp, firma):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Enlace vencido o inválido")
    try:
        local = almacenamiento().ruta_local(ruta)
    except ValueError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Ruta inválida")
    if not local.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Archivo no encontrado")
    return FileResponse(local, headers={"Cache-Control": "private, max-age=3600"})
