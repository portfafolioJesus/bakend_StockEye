from __future__ import annotations

from contextlib import asynccontextmanager
import logging
import mimetypes
from typing import Literal

from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel

from .configuracion import Configuracion
from .motor import MotorSegFormer
from .procesador import Servicio

log = logging.getLogger("stockeye.api")


class ImagenDisponible(BaseModel):
    id: str
    nombre: str
    sucursal_id: int
    sucursal: str
    imagenUrl: str
    actualizadaEn: str
    estado_medicion: str


def crear_app(cfg: Configuracion, *, motor_factory=MotorSegFormer, iniciar_servicios=True) -> FastAPI:
    servicio = Servicio(cfg, motor_factory)

    @asynccontextmanager
    async def lifespan(app):
        try:
            servicio.iniciar(ejecutar_hilos=iniciar_servicios)
            yield
        finally:
            servicio.detener()

    app = FastAPI(title="StockEye · Backend local", version="1.0.0", lifespan=lifespan,
        description="Procesa las carpetas de Sucursal 1 y 2. Los GET consultan resultados guardados; no ejecutan inferencia.")
    app.state.servicio = servicio

    def trabajo_completo(ident):
        try: servicio.archivos.carpeta(ident)
        except ValueError: raise HTTPException(404, "Análisis no encontrado.")
        trabajo = servicio.registro.obtener(ident)
        if trabajo is None: raise HTTPException(404, "Análisis no encontrado.")
        if trabajo["estado"] != "completada":
            raise HTTPException(409, {"mensaje": "El análisis no está completado.", "estado": trabajo["estado"]})
        return trabajo

    def leer_resultado(ident):
        trabajo = trabajo_completo(ident)
        try:
            documento = servicio.archivos.leer(ident)
            if documento["sucursal_id"] != trabajo["sucursal_id"] or documento["sha256_original"] != trabajo["sha256"]:
                raise ValueError("Resultado distinto del registrado.")
            return documento
        except (OSError, ValueError, KeyError, TypeError):
            log.exception("No se pudo leer el resultado %s", ident)
            raise HTTPException(503, "El análisis está registrado pero sus archivos no están disponibles.")

    def prefijo(request):
        return request.scope.get("root_path", "").rstrip("/")

    @app.get("/health", tags=["Conexión"])
    def salud(response: Response):
        response.headers["Cache-Control"] = "no-store"
        motor = servicio.motor
        return {
            "status": "ok", "servicio": "stockeye-backend-local",
            "modelo": {"disponible": motor is not None, "cargando": servicio.cargando_modelo,
                       "version": getattr(motor, "version", None), "dispositivo": getattr(motor, "dispositivo", None),
                       "error": servicio.error_modelo},
            "cola": servicio.registro.conteos(),
            "revision_segundos": cfg.revision_segundos,
            "ultima_revision": servicio.revisor.ultima_revision,
            "error_revision": servicio.revisor.ultimo_error,
        }

    @app.get("/api/imagenes", response_model=list[ImagenDisponible], tags=["Imágenes"])
    def imagenes(request: Request, response: Response,
                 sucursal_id: int | None = Query(None, ge=1, le=2),
                 limite: int = Query(100, ge=1, le=500), desde: int = Query(0, ge=0)):
        trabajos, total = servicio.registro.listar(sucursal_id, "completada", limite, desde)
        respuesta = []
        for trabajo in trabajos:
            d = leer_resultado(trabajo["id"])
            try: servicio.archivos.archivo(trabajo["id"], "superpuesta")
            except (OSError, ValueError, KeyError):
                raise HTTPException(503, "No se encontró una imagen marcada registrada.")
            respuesta.append(dict(id=trabajo["id"], nombre=trabajo["nombre"], sucursal_id=trabajo["sucursal_id"],
                sucursal=f"Sucursal {trabajo['sucursal_id']}",
                imagenUrl=f"{prefijo(request)}/api/imagenes/{trabajo['id']}/archivo",
                actualizadaEn=d["fecha_analisis"], estado_medicion=d["estado_medicion"]))
        response.headers["X-Total-Count"] = str(total)
        response.headers["Cache-Control"] = "no-store"
        return respuesta

    @app.get("/api/imagenes/{ident}", include_in_schema=False)
    @app.get("/api/analisis/{ident}", tags=["Resultados"])
    def analisis(ident: str, request: Request, response: Response):
        d = leer_resultado(ident)
        base = f"{prefijo(request)}/api/imagenes/{ident}"
        d["urls"] = {"superpuesta": base + "/archivo", "original": base + "/original", "mascara": base + "/mascara"}
        response.headers["Cache-Control"] = "no-store"
        return d

    def archivo(ident, tipo):
        leer_resultado(ident)
        try: ruta = servicio.archivos.archivo(ident, tipo)
        except (OSError, ValueError, KeyError, TypeError):
            raise HTTPException(404, "Archivo del análisis no encontrado.")
        media = {"superpuesta": "image/jpeg", "mascara": "image/png"}.get(tipo)
        media = media or mimetypes.guess_type(ruta.name)[0] or "application/octet-stream"
        return FileResponse(ruta, media_type=media, headers={"Cache-Control": "no-cache", "X-Content-Type-Options": "nosniff"})

    @app.get("/api/imagenes/{ident}/archivo", response_class=FileResponse, tags=["Imágenes"])
    def marcada(ident: str): return archivo(ident, "superpuesta")

    @app.get("/api/imagenes/{ident}/original", response_class=FileResponse, tags=["Imágenes"])
    def original(ident: str): return archivo(ident, "original")

    @app.get("/api/imagenes/{ident}/mascara", response_class=FileResponse, tags=["Imágenes"])
    def mascara(ident: str): return archivo(ident, "mascara")

    @app.get("/api/trabajos", tags=["Cola"])
    def trabajos(response: Response, sucursal_id: int | None = Query(None, ge=1, le=2),
                 estado: Literal["pendiente", "procesando", "completada", "error"] | None = None,
                 limite: int = Query(100, ge=1, le=500), desde: int = Query(0, ge=0)):
        filas, total = servicio.registro.listar(sucursal_id, estado, limite, desde)
        campos = ("id", "nombre", "sucursal_id", "estado", "creado_en", "iniciado_en", "terminado_en", "intentos", "error")
        response.headers["Cache-Control"] = "no-store"
        return {"total": total, "desde": desde, "limite": limite,
                "trabajos": [{k: f[k] for k in campos} for f in filas]}

    return app
