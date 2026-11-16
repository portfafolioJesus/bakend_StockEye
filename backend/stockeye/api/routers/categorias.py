"""Catálogo de categorías de producto (como los departamentos de Walmart)."""
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from ...core.db import todos, uno
from ...core.fotos import slug
from ..deps import ADMIN, Usuario, requiere, usuario_actual

router = APIRouter(tags=["categorías"])


@router.get("/categorias")
async def listar(request: Request, _: Usuario = Depends(usuario_actual)):
    async with request.app.state.db.tx() as conn:
        return await todos(conn, """SELECT id, codigo, nombre, departamento, orden FROM categoria
                                     WHERE activo ORDER BY orden, nombre""")


@router.get("/admin/categorias")
async def listar_admin(request: Request, _: Usuario = Depends(requiere(ADMIN))):
    async with request.app.state.db.tx() as conn:
        return await todos(conn, """
            SELECT c.*,
                   (SELECT count(*) FROM gondola g WHERE g.categoria_id = c.id AND g.activo) AS puntos,
                   (SELECT count(*) FROM ticket t WHERE t.categoria_id = c.id) AS tickets
              FROM categoria c ORDER BY c.activo DESC, c.orden, c.nombre""")


class CategoriaNueva(BaseModel):
    nombre: str = Field(min_length=2, max_length=80)
    departamento: str = Field(min_length=2, max_length=60)
    codigo: str | None = Field(None, max_length=30)
    orden: int = 100


class CategoriaCambio(BaseModel):
    nombre: str | None = Field(None, min_length=2, max_length=80)
    departamento: str | None = Field(None, min_length=2, max_length=60)
    orden: int | None = None
    activo: bool | None = None


@router.post("/admin/categorias", status_code=201)
async def crear(datos: CategoriaNueva, request: Request, u: Usuario = Depends(requiere(ADMIN))):
    codigo = slug(datos.codigo or datos.nombre, 30)
    async with request.app.state.db.tx(u.id) as conn:
        return await uno(conn, """INSERT INTO categoria (codigo, nombre, departamento, orden)
                                  VALUES (%s, %s, %s, %s) RETURNING *""",
                         [codigo, datos.nombre.strip(), datos.departamento.strip(), datos.orden])


@router.patch("/admin/categorias/{categoria_id}")
async def editar(categoria_id: int, datos: CategoriaCambio, request: Request, u: Usuario = Depends(requiere(ADMIN))):
    cambios = datos.model_dump(exclude_unset=True)
    if not cambios:
        raise HTTPException(422, "No hay cambios")
    sets = ", ".join(f"{k} = %s" for k in cambios)
    async with request.app.state.db.tx(u.id) as conn:
        fila = await uno(conn, f"UPDATE categoria SET {sets} WHERE id = %s RETURNING *", [*cambios.values(), categoria_id])
        if fila and "nombre" in cambios:      # el texto de las góndolas sigue al catálogo
            await conn.execute("UPDATE gondola SET categoria_id = categoria_id WHERE categoria_id = %s", [categoria_id])
    if not fila:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Categoría no encontrada")
    return fila
