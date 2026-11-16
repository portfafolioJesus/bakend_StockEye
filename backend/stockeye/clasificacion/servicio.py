"""Clasificación de productos visibles, independiente de la inferencia de vacío."""
from __future__ import annotations

import logging
import signal
import time
from collections.abc import Callable

from psycopg.types.json import Jsonb

from ..core.almacenamiento import almacenamiento
from ..core.config import Ajustes
from ..core.db import conectar, tx_sync
from ..ia.proveedor import ErrorIA, ProveedorIA, crear_proveedor
from ..ia.servicio import preparar_imagen
from .cupo import pausa_activa, registrar_pausa, registrar_recuperacion

log = logging.getLogger("stockeye.clasificador")
MAX_INTENTOS = 4


class Clasificador:
    def __init__(self, a: Ajustes, fabrica_proveedor: Callable | None = None):
        self.a = a
        self.nombre = a.worker_nombre + "-clasificacion"
        self.conn = conectar(a.database_url)
        self.detener = False
        self._ultimo_recinto = 0
        self._proxima_llamada = 0.0
        self._fabrica = fabrica_proveedor or crear_proveedor
        self._proveedor: ProveedorIA | None = None
        self._clave = None

    def proveedor(self, config: dict) -> ProveedorIA:
        clave = (config["proveedor"],config["modelo"],self.a.ia_modelo)
        if self._proveedor is None or clave != self._clave:
            self._proveedor = self._fabrica(config["proveedor"],self.a.ia_modelo or config["modelo"],self.a)
            self._clave = clave
        return self._proveedor

    def tomar(self) -> dict | None:
        if time.monotonic() < self._proxima_llamada:
            return None
        with tx_sync(self.conn):
            config = self.conn.execute("SELECT * FROM configuracion_ia").fetchone()
            if config and pausa_activa(self.conn,self.a,config):
                return None
            # Una petición dura como máximo el timeout HTTP. Recuperar un proceso caído no
            # vuelve a habilitar una respuesta vieja: cada claim incrementa la versión.
            self.conn.execute("""
                UPDATE tarea SET estado='PENDIENTE',tomada_por=NULL,tomada_en=NULL
                 WHERE tipo='CLASIFICAR_IMAGEN' AND estado='PROCESANDO'
                   AND tomada_en < now()-interval '5 minutes'""")
        # Soltar los candados de recuperación antes de bloquear imágenes:
        # la API manual usa Imagen -> Tarea y ese orden debe ser común.
        with tx_sync(self.conn):
            recintos = [f["recinto_id"] for f in self.conn.execute("""
                SELECT DISTINCT t.recinto_id FROM tarea t
                JOIN imagen i ON i.id=(t.payload->>'imagen_id')::bigint
                WHERE t.tipo='CLASIFICAR_IMAGEN' AND t.estado='PENDIENTE' AND t.disponible_en<=now()
                  AND i.estado_caracterizacion IN ('PENDIENTE','PROCESANDO')
                ORDER BY t.recinto_id""").fetchall()]
            orden = [r for r in recintos if r>self._ultimo_recinto]+[r for r in recintos if r<=self._ultimo_recinto]
            for recinto in orden:
                tarea = self.conn.execute("""
                    SELECT t.* FROM tarea t JOIN imagen i ON i.id=(t.payload->>'imagen_id')::bigint
                     WHERE t.tipo='CLASIFICAR_IMAGEN' AND t.estado='PENDIENTE'
                       AND t.disponible_en<=now() AND t.recinto_id=%s
                       AND i.estado_caracterizacion IN ('PENDIENTE','PROCESANDO')
                     ORDER BY t.creada_en,t.id LIMIT 1 FOR UPDATE OF i SKIP LOCKED""", [recinto]).fetchone()
                if not tarea:
                    continue
                fila = self.conn.execute("""
                    UPDATE imagen SET estado_caracterizacion='PROCESANDO',
                                      version_caracterizacion=version_caracterizacion+1
                     WHERE id=%s AND estado_caracterizacion IN ('PENDIENTE','PROCESANDO')
                     RETURNING version_caracterizacion""", [int(tarea["payload"]["imagen_id"])]).fetchone()
                if not fila:
                    continue
                tarea = self.conn.execute("""
                    UPDATE tarea SET estado='PROCESANDO',tomada_por=%s,tomada_en=now(),intentos=intentos+1,
                         payload=payload||%s WHERE id=%s RETURNING *""",
                    [self.nombre,Jsonb({"version_caracterizacion":fila["version_caracterizacion"]}),tarea["id"]]).fetchone()
                self._ultimo_recinto = recinto
                return tarea
        return None

    def procesar(self,tarea: dict) -> None:
        imagen_id = int(tarea["payload"]["imagen_id"])
        version = int(tarea["payload"]["version_caracterizacion"])
        with tx_sync(self.conn):
            config = self.conn.execute("SELECT * FROM configuracion_ia").fetchone()
            info = self.conn.execute("SELECT * FROM imagen WHERE id=%s", [imagen_id]).fetchone()
            categorias = self.conn.execute("SELECT id,codigo,nombre FROM categoria WHERE activo ORDER BY orden,nombre").fetchall()
            if not info or info["estado_caracterizacion"]=="MANUAL" or info["version_caracterizacion"]!=version:
                self.conn.execute("""UPDATE tarea SET estado='HECHA',terminada_en=now()
                                     WHERE id=%s AND tomada_por=%s
                                       AND (payload->>'version_caracterizacion')::int=%s""", [tarea["id"],self.nombre,version])
                return
        if not config or not config["activo"]:
            raise ErrorIA("La caracterización automática está desactivada",reintentable=False,motivo="CONFIGURACION")
        if not categorias:
            raise ErrorIA("No hay categorías activas",reintentable=False,motivo="CONFIGURACION")
        try:
            foto = almacenamiento().leer(info["ruta_archivo"])
        except (FileNotFoundError,ValueError) as e:
            raise ErrorIA("No se encuentra la fotografía almacenada",reintentable=False,motivo="ARCHIVO") from e
        jpg = preparar_imagen(foto,None,False)
        proveedor = self.proveedor(config)
        try:
            resultado = proveedor.clasificar(jpg,categorias)
        finally:
            self._proxima_llamada = time.monotonic()+getattr(self.a,"clasificacion_intervalo_llamadas_s",22.0)
        por_codigo = {c["codigo"]:c["id"] for c in categorias}
        categoria_id = por_codigo.get(resultado.categoria_codigo) if resultado.decision=="IDENTIFICADA" else None
        estado = "AUTOMATICA" if categoria_id is not None else "REVISION"
        detalle = {"decision":resultado.decision,"confianza":resultado.confianza,
                   "descripcion":resultado.descripcion,"proveedor":resultado.proveedor,"modelo":resultado.modelo,
                   "tokens_entrada":resultado.tokens_entrada,"tokens_salida":resultado.tokens_salida,
                   "latencia_ms":resultado.latencia_ms}
        with tx_sync(self.conn):
            self.conn.execute("SELECT pg_advisory_xact_lock(727006,%s)", [info["recinto_id"]])
            # Una categoría retirada durante la llamada debe quedar en revisión.
            if categoria_id is not None and not self.conn.execute(
                "SELECT id FROM categoria WHERE id=%s AND activo",[categoria_id]).fetchone():
                categoria_id,estado = None,"REVISION"
            actualizada = self.conn.execute("""
                UPDATE imagen SET categoria_id=%s,estado_caracterizacion=%s,producto_caracterizado=%s,
                    caracterizacion_detalle=caracterizacion_detalle||%s,
                    caracterizada_en=now(),caracterizada_por=NULL,
                    version_caracterizacion=version_caracterizacion+1
                 WHERE id=%s AND version_caracterizacion=%s AND estado_caracterizacion='PROCESANDO'
                 RETURNING id""", [categoria_id,estado,resultado.producto,Jsonb(detalle),imagen_id,version]).fetchone()
            if actualizada:
                self.conn.execute("SELECT fn_aplicar_caracterizacion(%s)",[imagen_id])
            self.conn.execute("""UPDATE tarea SET estado='HECHA',terminada_en=now(),error=NULL
                                 WHERE id=%s AND tomada_por=%s AND estado='PROCESANDO'
                                   AND (payload->>'version_caracterizacion')::int=%s""",[tarea["id"],self.nombre,version])
            registrar_recuperacion(self.conn,self.a,config)
        log.info("Imagen %s: caracterización %s",imagen_id,estado)

    def fallo(self,tarea: dict,error: Exception) -> None:
        imagen_id = int(tarea["payload"]["imagen_id"])
        version = int(tarea["payload"]["version_caracterizacion"])
        limite = isinstance(error,ErrorIA) and error.es_limite
        reintentar = limite or (getattr(error,"reintentable",True) and tarea["intentos"]<MAX_INTENTOS)
        espera = getattr(error,"esperar_s",None) or min(30*2**max(tarea["intentos"]-1,0),3600)
        mensaje = str(error)[:500] if isinstance(error,ErrorIA) else "Error interno de caracterización"
        with tx_sync(self.conn):
            self.conn.execute("SELECT pg_advisory_xact_lock(727006,%s)",[tarea["recinto_id"]])
            fila = self.conn.execute("""
                UPDATE imagen SET estado_caracterizacion=%s,
                    caracterizacion_detalle=caracterizacion_detalle||%s
                 WHERE id=%s AND version_caracterizacion=%s AND estado_caracterizacion='PROCESANDO'
                 RETURNING id""", ["PENDIENTE" if reintentar else "REVISION",
                   Jsonb({"error":mensaje,"motivo":getattr(error,"motivo",None)}),imagen_id,version]).fetchone()
            if not fila:
                self.conn.execute("""UPDATE tarea SET estado='HECHA',terminada_en=now()
                                     WHERE id=%s AND tomada_por=%s
                                       AND (payload->>'version_caracterizacion')::int=%s""",[tarea["id"],self.nombre,version])
                return
            self.conn.execute("""
                UPDATE tarea SET estado=%s,error=%s,tomada_por=NULL,tomada_en=NULL,
                    intentos=GREATEST(intentos-%s,0),disponible_en=now()+make_interval(secs=>%s),
                    terminada_en=CASE WHEN %s THEN NULL ELSE now() END
                 WHERE id=%s AND tomada_por=%s AND estado='PROCESANDO'
                   AND (payload->>'version_caracterizacion')::int=%s""",
                ["PENDIENTE" if reintentar else "ERROR",mensaje,1 if limite else 0,float(espera),reintentar,tarea["id"],self.nombre,version])
            if isinstance(error,ErrorIA) and (limite or error.motivo=="CONFIGURACION"):
                config = self.conn.execute("SELECT * FROM configuracion_ia").fetchone()
                if config:
                    registrar_pausa(self.conn,self.a,config,error,tarea["recinto_id"])
        log.warning("Imagen %s: %s (%s)",imagen_id,"reintento" if reintentar else "revisión manual",getattr(error,"motivo","INTERNO"))

    def procesar_seguro(self,tarea: dict) -> None:
        try:
            self.procesar(tarea)
        except Exception as error:
            if self.conn.info.transaction_status != 0:
                self.conn.rollback()
            self.fallo(tarea,error)

    def correr(self) -> None:
        signal.signal(signal.SIGTERM,lambda *_:setattr(self,"detener",True))
        signal.signal(signal.SIGINT,lambda *_:setattr(self,"detener",True))
        log.info("Clasificador iniciado; una llamada cada %ss como mínimo",
                 getattr(self.a,"clasificacion_intervalo_llamadas_s",22.0))
        try:
            while not self.detener:
                try:
                    tarea = self.tomar()
                    if tarea:
                        self.procesar_seguro(tarea)
                except Exception:
                    log.exception("Error revisando la cola de clasificación")
                    if self.conn.info.transaction_status != 0:
                        self.conn.rollback()
                intervalo = getattr(self.a,"clasificacion_intervalo_s",2.0)
                for _ in range(max(1,int(intervalo*10))):
                    if self.detener:
                        break
                    time.sleep(0.1)
        finally:
            self.conn.close()
