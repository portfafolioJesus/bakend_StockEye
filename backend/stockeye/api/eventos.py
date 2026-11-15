"""Hub de eventos en tiempo real: escucha PostgreSQL (LISTEN) y reparte a
los clientes SSE del panel web. Cada proceso de la api tiene su propio hub,
así que escala con las réplicas sin un broker adicional.
"""
from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field

import psycopg

log = logging.getLogger(__name__)
CANALES = ("ticket_evento", "notificacion_nueva", "imagen_procesada")


@dataclass(eq=False)
class Suscriptor:
    usuario_id: int
    recintos: set[int] | None          # None = todos
    cola: asyncio.Queue = field(default_factory=lambda: asyncio.Queue(maxsize=200))

    def le_interesa(self, canal: str, datos: dict) -> bool:
        if canal == "notificacion_nueva":
            return datos.get("usuario_id") == self.usuario_id
        recinto = datos.get("recinto_id")
        return self.recintos is None or recinto in self.recintos


class HubEventos:
    def __init__(self, dsn: str):
        self.dsn = dsn
        self.suscriptores: set[Suscriptor] = set()
        self._tarea: asyncio.Task | None = None
        self._detener = asyncio.Event()

    def iniciar(self) -> None:
        self._tarea = asyncio.create_task(self._escuchar(), name="hub-eventos")

    async def detener(self) -> None:
        self._detener.set()
        if self._tarea:
            self._tarea.cancel()
            try:
                await self._tarea
            except (asyncio.CancelledError, Exception):
                pass

    def suscribir(self, s: Suscriptor) -> None:
        self.suscriptores.add(s)

    def desuscribir(self, s: Suscriptor) -> None:
        self.suscriptores.discard(s)

    def publicar(self, canal: str, datos: dict) -> None:
        for s in list(self.suscriptores):
            if s.le_interesa(canal, datos):
                try:
                    s.cola.put_nowait((canal, datos))
                except asyncio.QueueFull:     # cliente lento: se descarta, el panel refresca igual
                    pass

    async def _escuchar(self) -> None:
        espera = 1
        while not self._detener.is_set():
            try:
                async with await psycopg.AsyncConnection.connect(self.dsn, autocommit=True) as conn:
                    for canal in CANALES:
                        await conn.execute(f"LISTEN {canal}")
                    espera = 1
                    log.info("Hub de eventos escuchando %s", ", ".join(CANALES))
                    async for n in conn.notifies():
                        try:
                            datos = json.loads(n.payload) if n.payload.startswith("{") else {"valor": n.payload}
                        except json.JSONDecodeError:
                            continue
                        self.publicar(n.channel, datos)
            except asyncio.CancelledError:
                raise
            except Exception as error:   # caída de la BD: reintenta con espera creciente
                log.warning("Hub de eventos desconectado (%s); reintento en %ss", error, espera)
                await asyncio.sleep(espera)
                espera = min(espera * 2, 30)
