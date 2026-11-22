from typing import Literal

import jwt
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from ...core.db import todos, uno
from ...core.seguridad import crear_token, hash_clave, leer_token, verificar_clave
from ..deps import Usuario, usuario_actual

router = APIRouter(prefix="/auth", tags=["auth"])


class Login(BaseModel):
    email: str = Field(min_length=3, max_length=160)
    clave: str = Field(min_length=1, max_length=200)
    origen: Literal["web", "app"] = "web"


class Refresco(BaseModel):
    refresco: str


class CambioClave(BaseModel):
    actual: str
    nueva: str = Field(min_length=8, max_length=200)


async def perfil(conn, usuario_id: int) -> dict:
    u = await uno(conn, """SELECT id, nombre, apellido, email, rol, telefono, debe_cambiar_clave, ultimo_acceso
                             FROM usuario WHERE id = %s""", [usuario_id])
    u["recintos"] = await todos(conn, """
        SELECT r.id, r.codigo, r.nombre, r.carpeta_imagenes, r.umbral_vacio
          FROM recinto r
         WHERE r.activo AND (%s = 'ADMINISTRADOR'
               OR r.id IN (SELECT recinto_id FROM usuario_recinto WHERE usuario_id = %s))
         ORDER BY r.codigo""", [u["rol"], usuario_id])
    return u


@router.post("/login")
async def login(datos: Login, request: Request):
    async with request.app.state.db.tx() as conn:
        u = await uno(conn, "SELECT id, rol, password_hash, activo FROM usuario WHERE lower(email) = lower(%s)",
                      [datos.email.strip()])
        if not u or not u["activo"] or not verificar_clave(datos.clave, u["password_hash"]):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Email o clave incorrectos")
        await conn.execute("UPDATE usuario SET ultimo_acceso = now(), ultimo_acceso_origen = %s WHERE id = %s",
                           [datos.origen, u["id"]])
        usuario = await perfil(conn, u["id"])
    return {"acceso": crear_token(u["id"], u["rol"]), "refresco": crear_token(u["id"], u["rol"], "refresco"),
            "usuario": usuario}


@router.post("/refresco")
async def refresco(datos: Refresco, request: Request):
    try:
        t = leer_token(datos.refresco, "refresco")
    except jwt.InvalidTokenError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sesión expirada, vuelve a ingresar")
    async with request.app.state.db.tx() as conn:
        u = await uno(conn, "SELECT id, rol FROM usuario WHERE id = %s AND activo", [int(t["sub"])])
    if not u:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Usuario inactivo")
    return {"acceso": crear_token(u["id"], u["rol"]), "refresco": crear_token(u["id"], u["rol"], "refresco")}


@router.get("/yo")
async def yo(request: Request, usuario: Usuario = Depends(usuario_actual)):
    async with request.app.state.db.tx() as conn:
        return await perfil(conn, usuario.id)


@router.post("/clave", status_code=204)
async def cambiar_clave(datos: CambioClave, request: Request, usuario: Usuario = Depends(usuario_actual)):
    async with request.app.state.db.tx(usuario.id) as conn:
        actual = await uno(conn, "SELECT password_hash FROM usuario WHERE id = %s", [usuario.id])
        if not verificar_clave(datos.actual, actual["password_hash"]):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "La clave actual no es correcta")
        await conn.execute("UPDATE usuario SET password_hash = %s, debe_cambiar_clave = FALSE WHERE id = %s",
                           [hash_clave(datos.nueva), usuario.id])
