"""Acceso a PostgreSQL con psycopg 3 (SQL explícito, sin ORM).

Cada transacción hecha en nombre de un usuario fija `app.usuario_id`
(SET LOCAL) para que los triggers registren quién hizo cada cambio.
"""
from __future__ import annotations

from contextlib import asynccontextmanager, contextmanager
from typing import Any, AsyncIterator, Iterator

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool


async def _configurar(conn: psycopg.AsyncConnection) -> None:
    await conn.set_autocommit(False)


class BaseDatos:
    """Pool asíncrono para la API."""

    def __init__(self, dsn: str, minimo: int = 1, maximo: int = 8):
        self.pool = AsyncConnectionPool(dsn, min_size=minimo, max_size=maximo, open=False,
                                        kwargs={"row_factory": dict_row}, configure=_configurar,
                                        name="stockeye-api")

    async def abrir(self) -> None:
        await self.pool.open(wait=True, timeout=30)

    async def cerrar(self) -> None:
        await self.pool.close()

    @asynccontextmanager
    async def tx(self, usuario_id: int | None = None) -> AsyncIterator[psycopg.AsyncConnection]:
        async with self.pool.connection() as conn:
            async with conn.transaction():
                await conn.execute("SELECT set_config('app.usuario_id', %s, true)",
                                   ["" if usuario_id is None else str(usuario_id)])
                yield conn


async def todos(conn: psycopg.AsyncConnection, sql: str, params: Any = None) -> list[dict]:
    cur = await conn.execute(sql, params)
    return await cur.fetchall()


async def uno(conn: psycopg.AsyncConnection, sql: str, params: Any = None) -> dict | None:
    cur = await conn.execute(sql, params)
    return await cur.fetchone()


async def valor(conn: psycopg.AsyncConnection, sql: str, params: Any = None) -> Any:
    fila = await uno(conn, sql, params)
    return None if fila is None else next(iter(fila.values()))


# ---- Versión síncrona para los microservicios (worker, notificador, IA) ----

def conectar(dsn: str, autocommit: bool = False) -> psycopg.Connection:
    return psycopg.connect(dsn, row_factory=dict_row, autocommit=autocommit,
                           application_name="stockeye-servicio")


@contextmanager
def tx_sync(conn: psycopg.Connection, usuario_id: int | None = None) -> Iterator[psycopg.Connection]:
    with conn.transaction():
        conn.execute("SELECT set_config('app.usuario_id', %s, true)", ["" if usuario_id is None else str(usuario_id)])
        yield conn
