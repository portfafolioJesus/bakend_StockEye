"""Aplicación FastAPI. La api nunca ejecuta inferencia: recibe, guarda,
encola y responde. El trabajo pesado lo hacen los microservicios.
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

import psycopg
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from psycopg import errors

from .. import __version__
from ..core import migraciones
from ..core.config import ajustes
from ..core.db import BaseDatos
from .eventos import HubEventos
from .routers import (admin, archivos, auth, categorias, dispositivos, eventos, imagenes, ingesta, notificaciones,
                      recintos, reportes, salud, tickets)

log = logging.getLogger("stockeye.api")


@asynccontextmanager
async def ciclo_de_vida(app: FastAPI):
    a = ajustes()
    a.validar_produccion()
    if a.auto_migrar:
        aplicadas = migraciones.aplicar(a.database_url, a.db_dir)
        if aplicadas:
            log.info("Migraciones aplicadas: %s", ", ".join(aplicadas))
    app.state.db = BaseDatos(a.database_url, a.db_pool_min, a.db_pool_max)
    await app.state.db.abrir()
    app.state.hub = HubEventos(a.database_url)
    app.state.hub.iniciar()
    yield
    await app.state.hub.detener()
    await app.state.db.cerrar()


def crear_app() -> FastAPI:
    a = ajustes()
    app = FastAPI(title="StockEye API", version=__version__, lifespan=ciclo_de_vida,
                  docs_url="/api/docs", openapi_url="/api/openapi.json", redoc_url=None)
    app.add_middleware(CORSMiddleware, allow_origins=a.lista_cors, allow_credentials=True,
                       allow_methods=["*"], allow_headers=["*"])

    # Errores de reglas de la BD (triggers / constraints) → respuestas claras
    @app.exception_handler(errors.CheckViolation)
    @app.exception_handler(errors.RaiseException)
    async def _regla(_: Request, e: psycopg.Error):
        return JSONResponse({"detail": (e.diag.message_primary or str(e))}, status_code=409)

    @app.exception_handler(errors.UniqueViolation)
    async def _unico(_: Request, e: psycopg.Error):
        return JSONResponse({"detail": "Ya existe un registro con esos datos", "restriccion": e.diag.constraint_name},
                            status_code=409)

    @app.exception_handler(errors.ForeignKeyViolation)
    async def _fk(_: Request, e: psycopg.Error):
        return JSONResponse({"detail": "Referencia inválida (otro recinto o registro inexistente)",
                             "restriccion": e.diag.constraint_name}, status_code=422)

    prefijo = "/api/v1"
    for r in (salud, auth, ingesta, imagenes, tickets, recintos, categorias, notificaciones, dispositivos, eventos,
              archivos, admin, reportes):
        app.include_router(r.router, prefix=prefijo)
    return app


app = crear_app()
