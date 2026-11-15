"""Microservicio que completa "producto faltante" con IA (Groq por defecto).

Consume la cola `tarea` (tipo ANALISIS_IA) con SKIP LOCKED. Va separado del
worker de inferencia porque es lento, tiene límite de uso y depende de
internet: si Groq falla, la detección de vacíos sigue funcionando.
"""
from __future__ import annotations

import io
import logging
import signal
import time

import numpy as np
from PIL import Image, ImageOps
from psycopg.types.json import Jsonb

from ..core.almacenamiento import almacenamiento, ruta_anotada
from ..core.config import Ajustes
from ..core.db import conectar, tx_sync
from ..inferencia.motor import recortar_roi
from .proveedor import ErrorIA, ProveedorIA, crear_proveedor

log = logging.getLogger("stockeye.ia")
MAX_INTENTOS = 4


def preparar_imagen(datos: bytes, roi: list | None, recortar: bool, lado_max: int = 1280) -> bytes:
    """Recorta a la góndola (privacidad: no enviar clientes) y reduce a ≤1280 px."""
    try:
        img = ImageOps.exif_transpose(Image.open(io.BytesIO(datos))).convert("RGB")
    except Exception as e:
        raise ErrorIA("Imagen ilegible", reintentable=False) from e
    if recortar and roi:
        img = Image.fromarray(recortar_roi(np.asarray(img), roi))
    img.thumbnail((lado_max, lado_max), Image.Resampling.LANCZOS)
    salida = io.BytesIO()
    img.save(salida, "JPEG", quality=85)
    return salida.getvalue()


class EnriquecedorIA:
    def __init__(self, a: Ajustes):
        self.a = a
        self.nombre = a.worker_nombre
        self.conn = conectar(a.database_url)
        self.escucha = conectar(a.database_url, autocommit=True)
        self.detener = False
        self._proveedor: ProveedorIA | None = None
        self._clave_config = None

    def proveedor(self, config: dict) -> ProveedorIA:
        clave = (config["proveedor"], config["modelo"])
        if self._proveedor is None or clave != self._clave_config:
            self._proveedor = crear_proveedor(config["proveedor"], config["modelo"], self.a)
            self._clave_config = clave
            log.info("Proveedor de IA: %s · modelo %s", self._proveedor.nombre, self._proveedor.modelo)
        return self._proveedor

    def tomar(self) -> dict | None:
        with tx_sync(self.conn):
            return self.conn.execute("""
                UPDATE tarea SET estado = 'PROCESANDO', tomada_por = %s, tomada_en = now(), intentos = intentos + 1
                 WHERE id = (SELECT id FROM tarea WHERE tipo = 'ANALISIS_IA' AND estado = 'PENDIENTE'
                                AND disponible_en <= now()
                              ORDER BY disponible_en LIMIT 1 FOR UPDATE SKIP LOCKED)
                RETURNING *""", [self.nombre]).fetchone()

    def procesar(self, tarea: dict) -> None:
        imagen_id = int(tarea["payload"]["imagen_id"])
        with tx_sync(self.conn):
            config = self.conn.execute("SELECT * FROM configuracion_ia").fetchone()
            info = self.conn.execute("""
                SELECT i.ruta_archivo, g.codigo AS gondola, COALESCE(cat.nombre, g.categoria) AS categoria, c.roi, p.porcentaje_vacio,
                       p.ruta_imagen_anotada
                  FROM imagen i LEFT JOIN gondola g ON g.id = i.gondola_id LEFT JOIN camara c ON c.id = i.camara_id
                  LEFT JOIN categoria cat ON cat.id = COALESCE(i.categoria_id, g.categoria_id)
                  LEFT JOIN LATERAL (SELECT * FROM prediccion WHERE imagen_id = i.id ORDER BY creada_en DESC LIMIT 1) p ON TRUE
                 WHERE i.id = %s""", [imagen_id]).fetchone()
        if not config["activo"]:
            raise ErrorIA("La integración de IA está desactivada", reintentable=False)
        if not info:
            raise ErrorIA("Imagen inexistente", reintentable=False)
        # La imagen anotada (con los vacíos marcados) ayuda al modelo a ubicar el hueco.
        ruta = info["ruta_imagen_anotada"] or ruta_anotada(info["ruta_archivo"])
        if not almacenamiento().existe(ruta):
            ruta = info["ruta_archivo"]
        jpg = preparar_imagen(almacenamiento().leer(ruta), info["roi"], config["recortar_a_gondola"])
        r = self.proveedor(config).analizar(jpg, {"gondola": info["gondola"], "categoria": info["categoria"],
                                                  "porcentaje_vacio": info["porcentaje_vacio"]})
        with tx_sync(self.conn):
            ticket_id = self.conn.execute("SELECT (payload ->> 'ticket_id')::BIGINT AS t FROM tarea WHERE id = %s",
                                          [tarea["id"]]).fetchone()["t"]      # pudo llegar mientras se analizaba
            analisis = self.conn.execute("""
                INSERT INTO analisis_ia (ticket_id, imagen_id, proveedor, modelo, productos_faltantes, resumen,
                                         tokens_entrada, tokens_salida, latencia_ms, exitoso)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, TRUE) RETURNING id""",
                [ticket_id, imagen_id, r.proveedor, r.modelo, Jsonb(r.productos), r.resumen, r.tokens_entrada,
                 r.tokens_salida, r.latencia_ms]).fetchone()["id"]
            if ticket_id:
                self.conn.execute("SELECT fn_aplicar_analisis_ia(%s, %s)", [analisis, ticket_id])
            self.conn.execute("UPDATE tarea SET estado = 'HECHA', terminada_en = now(), error = NULL WHERE id = %s",
                              [tarea["id"]])
        top = r.productos[0]["producto"] if r.productos else "sin resultado"
        log.info("IA imagen %s: %s (%s ms)", imagen_id, top, r.latencia_ms)

    def fallo(self, tarea: dict, e: Exception) -> None:
        reintentable = getattr(e, "reintentable", True) and tarea["intentos"] < MAX_INTENTOS
        espera = getattr(e, "esperar_s", None) or 30 * 2 ** (tarea["intentos"] - 1)
        log.warning("IA tarea %s falló (%s): %s", tarea["id"], "reintento" if reintentable else "definitivo", e)
        if self.conn.info.transaction_status != 0:
            self.conn.rollback()
        with tx_sync(self.conn):
            self.conn.execute("""
                UPDATE tarea SET estado = %s, error = %s, tomada_por = NULL,
                       disponible_en = now() + make_interval(secs => %s),
                       terminada_en = CASE WHEN %s THEN NULL ELSE now() END
                 WHERE id = %s""", ["PENDIENTE" if reintentable else "ERROR", str(e)[:1000], espera, reintentable,
                                    tarea["id"]])
            if not reintentable:
                self.conn.execute("""
                    INSERT INTO analisis_ia (ticket_id, imagen_id, proveedor, modelo, exitoso, error_detalle)
                    SELECT (t.payload ->> 'ticket_id')::BIGINT, (t.payload ->> 'imagen_id')::BIGINT,
                           c.proveedor, c.modelo, FALSE, %s
                      FROM tarea t, configuracion_ia c WHERE t.id = %s""", [str(e)[:1000], tarea["id"]])

    def correr(self) -> None:
        signal.signal(signal.SIGTERM, lambda *_: setattr(self, "detener", True))
        signal.signal(signal.SIGINT, lambda *_: setattr(self, "detener", True))
        self.escucha.execute("LISTEN tarea_nueva")
        log.info("Enriquecedor de IA iniciado")
        while not self.detener:
            try:
                while not self.detener and (t := self.tomar()):
                    try:
                        self.procesar(t)
                    except Exception as e:
                        self.fallo(t, e)
            except Exception:
                log.exception("Error en el enriquecedor; reintento en 10 s")
                time.sleep(10)
            for _ in self.escucha.notifies(timeout=5, stop_after=1):
                pass
        self.conn.close()
        self.escucha.close()
