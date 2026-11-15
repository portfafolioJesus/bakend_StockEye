"""Microservicio de inferencia.

* Toma imágenes PENDIENTE con FOR UPDATE SKIP LOCKED: N réplicas nunca
  procesan la misma foto.
* Turnos por recinto (round-robin): si R01 manda una ráfaga, R02 igual
  entra en el siguiente ciclo. Con WORKER_RECINTOS=R01 el worker queda
  dedicado a ese recinto.
* Lease: si el worker muere a mitad de camino, fn_recuperar_imagenes()
  devuelve la foto a la cola (máx. 3 intentos).
* Se despierta con LISTEN imagen_nueva y recarga el modelo con
  LISTEN modelo_activado (cambio desde el panel de administración).
"""
from __future__ import annotations

import logging
import os
import signal
import time
import traceback
from pathlib import Path

from ..core.almacenamiento import almacenamiento, ruta_anotada
from ..core.config import Ajustes
from ..core.db import conectar, tx_sync
from .motor import MotorVacio

log = logging.getLogger("stockeye.worker")
LATIDO = Path(os.environ.get("STOCKEYE_LATIDO", "/tmp/stockeye-worker.latido"))


class ErrorPermanente(Exception):
    """La foto no se puede procesar nunca (archivo faltante o corrupto): va directo a ERROR."""


def crear_motor(modelo: dict, a: Ajustes) -> MotorVacio:
    ruta = a.modelos_dir / Path(modelo["ruta_pesos"]).name
    p = modelo.get("parametros") or {}
    hilos = a.ort_hilos or p.get("hilos_recomendados") or max(1, (os.cpu_count() or 2) // 2)
    if modelo["familia"] == "SEGFORMER":
        from .segformer_onnx import MotorSegFormerOnnx
        return MotorSegFormerOnnx(ruta, lado=p.get("lado", 1280), pixeles_max=p.get("pixeles_max", 600_000),
                                  umbral_vacio=float(modelo["umbral_confianza"]), parametros=p, hilos=hilos,
                                  dispositivo=a.inferencia_dispositivo)
    if modelo["familia"] == "YOLO":
        from .yolo_onnx import MotorYoloOnnx
        return MotorYoloOnnx(ruta, clases=modelo["clases"] or {}, umbral_confianza=float(modelo["umbral_confianza"]),
                             imgsz=p.get("imgsz", 640), hilos=hilos, dispositivo=a.inferencia_dispositivo)
    raise ValueError(f"Familia de modelo no soportada: {modelo['familia']}")


class WorkerInferencia:
    def __init__(self, a: Ajustes, fabrica_motor=crear_motor):
        self.a = a
        self.nombre = a.worker_nombre
        self.fabrica_motor = fabrica_motor
        codigos = a.worker_recintos.strip()
        self.codigos = None if codigos in ("", "*") else [c.strip().upper() for c in codigos.split(",") if c.strip()]
        self.conn = conectar(a.database_url)
        self.escucha = conectar(a.database_url, autocommit=True)
        self.motor: MotorVacio | None = None
        self.modelo: dict | None = None
        self.recargar = True
        self.detener = False
        self._ultimo_recinto = 0
        self.procesadas = 0

    # ------------------------------------------------------------ modelo
    def cargar_modelo(self) -> None:
        with tx_sync(self.conn):
            m = self.conn.execute("SELECT * FROM modelo_ia WHERE activo").fetchone()
        if not m:
            log.error("No hay modelo activo en modelo_ia: registra uno con 'stockeye modelo registrar'")
            self.motor, self.modelo = None, None
            return
        try:
            motor = self.fabrica_motor(m, self.a)
        except Exception:
            log.exception("No se pudo cargar el modelo %s %s", m["nombre"], m["version"])
            self.motor, self.modelo = None, None
            return
        self.motor, self.modelo = motor, m
        log.info("Modelo activo: %s %s (%s)", m["nombre"], m["version"], getattr(motor, "descripcion", ""))

    # ------------------------------------------------------------ cola
    def recintos_permitidos(self) -> list[int] | None:
        if self.codigos is None:
            return None
        filas = self.conn.execute("SELECT id FROM recinto WHERE codigo = ANY(%s)", [self.codigos]).fetchall()
        return [f["id"] for f in filas]

    def tomar(self) -> dict | None:
        """Turno rotativo entre los recintos que tienen fotos pendientes."""
        with tx_sync(self.conn):
            permitidos = self.recintos_permitidos()
            pendientes = [f["recinto_id"] for f in self.conn.execute(
                """SELECT DISTINCT recinto_id FROM imagen
                    WHERE estado = 'PENDIENTE' AND (%s::int[] IS NULL OR recinto_id = ANY(%s::int[]))
                    ORDER BY recinto_id""", [permitidos, permitidos]).fetchall()]
            if not pendientes:
                return None
            orden = [r for r in pendientes if r > self._ultimo_recinto] + \
                    [r for r in pendientes if r <= self._ultimo_recinto]
            for recinto_id in orden:
                fila = self.conn.execute("""
                    UPDATE imagen SET estado = 'PROCESANDO', tomada_por = %s, tomada_en = now(),
                                      intentos = intentos + 1
                     WHERE id = (SELECT id FROM imagen
                                  WHERE estado = 'PENDIENTE' AND recinto_id = %s
                                  ORDER BY recibida_en LIMIT 1
                                  FOR UPDATE SKIP LOCKED)
                    RETURNING id, recinto_id, gondola_id, camara_id, origen, ruta_archivo, ancho_px, alto_px,
                              intentos""", [self.nombre, recinto_id]).fetchone()
                if fila:
                    self._ultimo_recinto = recinto_id
                    return fila
        return None

    # ------------------------------------------------------------ proceso
    def procesar(self, img: dict) -> None:
        assert self.motor and self.modelo
        try:
            datos = almacenamiento().leer(img["ruta_archivo"])
        except (FileNotFoundError, ValueError) as e:
            raise ErrorPermanente(f"No se encontró el archivo {img['ruta_archivo']}") from e
        roi = None
        if img["camara_id"]:
            fila = self.conn.execute("SELECT roi FROM camara WHERE id = %s", [img["camara_id"]]).fetchone()
            self.conn.rollback()
            roi = fila["roi"] if fila else None
        tamano = (img["ancho_px"], img["alto_px"]) if img["ancho_px"] else None
        try:
            r = self.motor.inferir_bytes(datos, roi, tamano)
        except ValueError as e:
            raise ErrorPermanente(str(e)) from e
        ruta_pred = ruta_anotada(img["ruta_archivo"])
        almacenamiento().guardar(ruta_pred, r.anotada_jpg)

        with tx_sync(self.conn):                       # app.usuario_id vacío = "sistema"
            c = self.conn
            pred_id = c.execute("""
                INSERT INTO prediccion (imagen_id, modelo_id, porcentaje_vacio, umbral_aplicado, num_vacios,
                                        num_productos, tiempo_inferencia_ms, ruta_imagen_anotada)
                SELECT %s, %s, %s, r.umbral_vacio, %s, %s, %s, %s FROM recinto r WHERE r.id = %s
                ON CONFLICT (imagen_id, modelo_id) DO UPDATE
                   SET porcentaje_vacio = EXCLUDED.porcentaje_vacio, umbral_aplicado = EXCLUDED.umbral_aplicado,
                       num_vacios = EXCLUDED.num_vacios, num_productos = EXCLUDED.num_productos,
                       tiempo_inferencia_ms = EXCLUDED.tiempo_inferencia_ms,
                       ruta_imagen_anotada = EXCLUDED.ruta_imagen_anotada, creada_en = now()
                RETURNING id, supera_umbral""",
                [img["id"], self.modelo["id"], r.porcentaje_vacio, r.num_vacios, r.num_productos, r.ms_inferencia,
                 ruta_pred, img["recinto_id"]]).fetchone()
            c.execute("DELETE FROM deteccion WHERE prediccion_id = %s", [pred_id["id"]])
            if r.regiones:
                with c.cursor() as cur:
                    cur.executemany("""INSERT INTO deteccion (prediccion_id, clase, confianza, x_min, y_min, x_max, y_max)
                                       VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                                    [(pred_id["id"], g.clase, g.confianza, g.x_min, g.y_min, g.x_max, g.y_max)
                                     for g in r.regiones])
            c.execute("""UPDATE imagen SET estado = 'PROCESADA', procesada_en = now(), error_detalle = NULL,
                                           ancho_px = COALESCE(ancho_px, %s), alto_px = COALESCE(alto_px, %s)
                          WHERE id = %s""", [r.ancho_px, r.alto_px, img["id"]])
            ticket = None
            if img["origen"] == "CAMARA":
                # Regla principal de la BD: ticket nuevo o SEGUIMIENTO del abierto
                ticket = c.execute("SELECT fn_ticket_desde_prediccion(%s) AS t", [pred_id["id"]]).fetchone()["t"]
                if ticket:
                    tipo = c.execute("SELECT tipo FROM ticket_imagen WHERE ticket_id = %s AND imagen_id = %s",
                                     [ticket, img["id"]]).fetchone()
                    if tipo and tipo["tipo"] == "APERTURA":
                        c.execute("SELECT fn_encolar_analisis_ia(%s, %s)", [img["id"], ticket])
            elif pred_id["supera_umbral"]:
                es_cierre = c.execute("SELECT EXISTS (SELECT 1 FROM ticket_imagen WHERE imagen_id = %s AND tipo = 'CIERRE') e",
                                      [img["id"]]).fetchone()["e"]
                if not es_cierre:   # foto móvil nueva: la sugerencia de IA aparece en "Resultado del análisis"
                    c.execute("SELECT fn_encolar_analisis_ia(%s, NULL)", [img["id"]])
        self.procesadas += 1
        nivel = logging.WARNING if r.ms_inferencia > self.a.inferencia_presupuesto_s * 1000 else logging.INFO
        log.log(nivel, "imagen %s recinto %s: %.2f %% vacío, %s cajas, %s ms%s%s", img["id"], img["recinto_id"],
                r.porcentaje_vacio, r.num_vacios, r.ms_inferencia,
                f" → ticket {ticket}" if ticket else "",
                " (EXCEDE el presupuesto de tiempo)" if nivel == logging.WARNING else "")

    def procesar_seguro(self, img: dict) -> None:
        try:
            self.procesar(img)
        except Exception as e:
            permanente = isinstance(e, ErrorPermanente)
            log.error("imagen %s falló (%s): %s", img["id"], "permanente" if permanente else f"intento {img['intentos']}", e)
            if self.conn.info.transaction_status != 0:
                self.conn.rollback()
            with tx_sync(self.conn):
                self.conn.execute("""
                    UPDATE imagen
                       SET estado = CASE WHEN %s OR intentos >= 3 THEN 'ERROR'::estado_procesamiento
                                         ELSE 'PENDIENTE' END,
                           error_detalle = %s, tomada_por = NULL
                     WHERE id = %s""", [permanente, f"{e}\n{traceback.format_exc(limit=3)}"[:4000], img["id"]])

    # ------------------------------------------------------------ bucle
    def _atender_eventos(self, espera: float) -> None:
        for n in self.escucha.notifies(timeout=espera, stop_after=1):
            if n.channel == "modelo_activado":
                log.info("Cambio de modelo activo (id %s): recargando", n.payload)
                self.recargar = True

    def correr(self) -> None:
        signal.signal(signal.SIGTERM, lambda *_: setattr(self, "detener", True))
        signal.signal(signal.SIGINT, lambda *_: setattr(self, "detener", True))
        self.escucha.execute("LISTEN imagen_nueva")
        self.escucha.execute("LISTEN modelo_activado")
        log.info("Worker %s iniciado · recintos: %s", self.nombre, ", ".join(self.codigos) if self.codigos else "todos")
        ultimo_recolector = 0.0
        while not self.detener:
            LATIDO.write_text(str(time.time()))
            if self.recargar:
                self.recargar = False
                self.cargar_modelo()
            if time.monotonic() - ultimo_recolector > 60:
                ultimo_recolector = time.monotonic()
                with tx_sync(self.conn):
                    n = self.conn.execute("SELECT fn_recuperar_imagenes(%s) n", [self.a.lease_minutos]).fetchone()["n"]
                if n:
                    log.warning("%s imágenes recuperadas de workers caídos", n)
            if self.motor:
                while not self.detener and not self.recargar and (img := self.tomar()):
                    self.procesar_seguro(img)
                    LATIDO.write_text(str(time.time()))
                    self._atender_eventos(0.001)
            self._atender_eventos(5 if self.motor else 15)
        log.info("Worker detenido (%s imágenes procesadas)", self.procesadas)
        self.conn.close()
        self.escucha.close()
