"""Dependencias comunes: usuario autenticado, roles y alcance por recinto."""
from __future__ import annotations

from dataclasses import dataclass, field

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from ..core.db import BaseDatos, todos, uno
from ..core.seguridad import leer_token

ADMIN, SUPERVISOR, REPONEDOR = "ADMINISTRADOR", "SUPERVISOR", "REPONEDOR"
_bearer = HTTPBearer(auto_error=False)


@dataclass
class Usuario:
    id: int
    nombre: str
    apellido: str
    email: str
    rol: str
    recintos: list[int] = field(default_factory=list)

    @property
    def es_admin(self) -> bool:
        return self.rol == ADMIN

    def ve_recinto(self, recinto_id: int) -> bool:
        return self.es_admin or recinto_id in self.recintos


def db(request: Request) -> BaseDatos:
    return request.app.state.db


async def cargar_usuario(base: BaseDatos, usuario_id: int) -> Usuario | None:
    async with base.tx() as conn:
        u = await uno(conn, "SELECT id, nombre, apellido, email, rol FROM usuario WHERE id = %s AND activo",
                      [usuario_id])
        if not u:
            return None
        rec = await todos(conn, "SELECT recinto_id FROM usuario_recinto WHERE usuario_id = %s", [usuario_id])
    return Usuario(recintos=[r["recinto_id"] for r in rec], **u)


async def usuario_desde_token(base: BaseDatos, token: str | None) -> Usuario:
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Falta el token", headers={"WWW-Authenticate": "Bearer"})
    try:
        datos = leer_token(token)
    except jwt.ExpiredSignatureError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sesión expirada", headers={"WWW-Authenticate": "Bearer"})
    except jwt.InvalidTokenError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token inválido", headers={"WWW-Authenticate": "Bearer"})
    usuario = await cargar_usuario(base, int(datos["sub"]))
    if not usuario:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Usuario inactivo")
    return usuario


async def usuario_actual(request: Request,
                         cred: HTTPAuthorizationCredentials | None = Depends(_bearer)) -> Usuario:
    return await usuario_desde_token(request.app.state.db, cred.credentials if cred else None)


def requiere(*roles: str):
    async def _dep(usuario: Usuario = Depends(usuario_actual)) -> Usuario:
        if usuario.rol not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "No tienes permiso para esta acción")
        return usuario
    return _dep


def exigir_recinto(usuario: Usuario, recinto_id: int) -> None:
    if not usuario.ve_recinto(recinto_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "No tienes acceso a este recinto")


def recintos_visibles(usuario: Usuario) -> list[int] | None:
    """None = todos (administrador)."""
    return None if usuario.es_admin else usuario.recintos
