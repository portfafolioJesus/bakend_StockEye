"""Microservicio de notificaciones push.

Las notificaciones las crean la BD (triggers) y la api en la tabla
`notificacion`. Este servicio las envía por FCM (app) y Web Push (panel),
marca `enviada_push` y elimina los destinos que ya no existen.
"""
from __future__ import annotations

import json
import logging
import signal
import time

from ..core.config import Ajustes
from ..core.db import conectar
from .fcm import ClienteFCM, TokenInvalido

log = logging.getLogger("stockeye.notificador")
TITULOS = {"ALERTA_VACIO": "Vacío detectado", "TICKET_ASIGNADO": "Nuevo ticket asignado",
           "TICKET_CERRADO": "Ticket cerrado", "COMENTARIO": "Nuevo comentario"}
MAX_INTENTOS = 5


class Notificador:
    def __init__(self, a: Ajustes):
        self.a = a
        self.conn = conectar(a.database_url)
        self.escucha = conectar(a.database_url, autocommit=True)
        self.fcm = None
        if a.fcm_credenciales and a.fcm_credenciales.is_file():
            self.fcm = ClienteFCM(a.fcm_credenciales)
            log.info("FCM habilitado (proyecto %s)", self.fcm.proyecto)
        else:
            log.warning("FCM deshabilitado: define FCM_CREDENCIALES con el JSON de la cuenta de servicio")
        self.webpush = bool(a.vapid_privada and a.vapid_publica)
        if not self.webpush:
            log.warning("Web Push deshabilitado: genera claves con 'stockeye vapid' y define VAPID_*")
        self.detener = False

    def _enviar_web(self, sub: dict, carga: dict) -> bool:
        from pywebpush import WebPushException, webpush
        try:
            webpush(subscription_info={"endpoint": sub["endpoint"], "keys": {"p256dh": sub["p256dh"], "auth": sub["auth"]}},
                    data=json.dumps(carga), vapid_private_key=self.a.vapid_privada,
                    vapid_claims={"sub": self.a.vapid_contacto}, ttl=3600, timeout=10)
            return True
        except WebPushException as e:
            codigo = getattr(e.response, "status_code", None)
            if codigo in (404, 410):
                self.conn.execute("DELETE FROM web_push_suscripcion WHERE id = %s", [sub["id"]])
                return False
            raise

    def procesar_lote(self) -> int:
        """Envía hasta 20 notificaciones. Las filas quedan bloqueadas (SKIP LOCKED)
        mientras se envían, así varias réplicas no duplican el push."""
        with self.conn.transaction():
            filas = self.conn.execute("""
                SELECT n.id, n.usuario_id, n.tipo, n.mensaje, n.ticket_id, t.numero
                  FROM notificacion n LEFT JOIN ticket t ON t.id = n.ticket_id
                 WHERE NOT n.enviada_push AND n.intentos_push < %s AND n.creada_en > now() - interval '1 day'
                 ORDER BY n.creada_en LIMIT 20
                 FOR UPDATE OF n SKIP LOCKED""", [MAX_INTENTOS]).fetchall()
            for n in filas:
                titulo = TITULOS.get(n["tipo"], "StockEye")
                datos = {"tipo": n["tipo"], "numero": n["numero"], "notificacion_id": str(n["id"]),
                         "url": f"/tickets/{n['numero']}" if n["numero"] else "/"}
                enviados, errores = 0, []
                tokens = self.conn.execute("SELECT id, token FROM dispositivo_push WHERE usuario_id = %s",
                                           [n["usuario_id"]]).fetchall()
                subs = self.conn.execute("SELECT * FROM web_push_suscripcion WHERE usuario_id = %s",
                                         [n["usuario_id"]]).fetchall()
                if self.fcm:
                    for d in tokens:
                        try:
                            self.fcm.enviar(d["token"], titulo, n["mensaje"], datos)
                            enviados += 1
                        except TokenInvalido:
                            self.conn.execute("DELETE FROM dispositivo_push WHERE id = %s", [d["id"]])
                        except Exception as e:
                            errores.append(f"fcm: {e}")
                if self.webpush:
                    for s in subs:
                        try:
                            enviados += self._enviar_web(s, {"titulo": titulo, "cuerpo": n["mensaje"], **datos})
                        except Exception as e:
                            errores.append(f"webpush: {e}")
                sin_destino = not tokens and not subs
                listo = enviados > 0 or sin_destino or not errores
                self.conn.execute("""
                    UPDATE notificacion SET enviada_push = %s, intentos_push = intentos_push + 1,
                           push_enviada_en = CASE WHEN %s THEN now() END, push_error = %s
                     WHERE id = %s""", [listo, enviados > 0,
                                        "; ".join(errores)[:500] or ("sin dispositivos" if sin_destino else None), n["id"]])
                if enviados:
                    log.info("push %s (%s) → usuario %s: %s destino(s)", n["id"], n["tipo"], n["usuario_id"], enviados)
        return len(filas)

    def correr(self) -> None:
        signal.signal(signal.SIGTERM, lambda *_: setattr(self, "detener", True))
        signal.signal(signal.SIGINT, lambda *_: setattr(self, "detener", True))
        self.escucha.execute("LISTEN notificacion_nueva")
        log.info("Notificador iniciado")
        while not self.detener:
            try:
                while not self.detener and self.procesar_lote():
                    pass
            except Exception:
                log.exception("Error enviando notificaciones; reintento en 10 s")
                time.sleep(10)
            for _ in self.escucha.notifies(timeout=5, stop_after=1):
                pass
        self.conn.close()
        self.escucha.close()
