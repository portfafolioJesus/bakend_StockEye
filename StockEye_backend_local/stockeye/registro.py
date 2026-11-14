from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

DB_LOCK_KEY = 0x53544F434B455945


def ahora() -> str:
    return datetime.now(timezone.utc).isoformat()


class InstanciaPerdida(RuntimeError):
    """La sesión que protegía la cola dejó de estar disponible."""


class Registro:
    """Cola PostgreSQL; no crea tablas ni cambia de motor automáticamente."""

    def __init__(self, dsn: str, *, connect_timeout: int = 5,
                 statement_timeout_ms: int = 20_000):
        if not dsn or connect_timeout < 1 or statement_timeout_ms < 1:
            raise ValueError("Falta una conexión PostgreSQL válida.")
        self._dsn = dsn
        self._connect_timeout = connect_timeout
        self._statement_timeout_ms = statement_timeout_ms
        self._instancia = None

    def _conectar(self, *, autocommit=False):
        return psycopg.connect(
            self._dsn, connect_timeout=self._connect_timeout,
            row_factory=dict_row, autocommit=autocommit,
            application_name="stockeye-backend-local",
        )

    def _tiempos(self, db, *, local=True):
        db.execute(
            "SELECT set_config('statement_timeout', %s, %s), "
            "set_config('lock_timeout', %s, %s)",
            (str(self._statement_timeout_ms), local,
             str(self._statement_timeout_ms), local),
        )

    @contextmanager
    def conexion(self):
        if self._instancia is not None:
            self.verificar_instancia()
        with self._conectar() as db:
            self._tiempos(db)
            yield db

    def comprobar_version_esquema(self):
        archivo = Path(__file__).resolve().parents[1] / "migraciones" / "001_cola.sql"
        if not archivo.is_file():
            raise RuntimeError("Falta el archivo de migración PostgreSQL 001_cola.sql.")
        esperada = hashlib.sha256(archivo.read_bytes()).hexdigest()
        with self.conexion() as db:
            if db.execute("SELECT to_regclass('public.schema_migrations') AS t").fetchone()["t"] is None:
                raise RuntimeError("Faltan las migraciones PostgreSQL. Consulte docs/POSTGRESQL.md.")
            aplicada = db.execute(
                "SELECT sha256 FROM public.schema_migrations WHERE version='001'"
            ).fetchone()
            columnas = db.execute(
                "SELECT table_name,column_name FROM information_schema.columns "
                "WHERE table_schema='public' AND table_name IN ('trabajos','observaciones')"
            ).fetchall()
        requeridas = {
            "trabajos": {"secuencia", "id", "sucursal_id", "relativo", "nombre", "sha256",
                         "copia", "estado", "creado_en", "iniciado_en", "terminado_en",
                         "intentos", "error"},
            "observaciones": {"sucursal_id", "relativo", "firma", "visto_desde", "registrado"},
        }
        presentes = {tabla: set() for tabla in requeridas}
        for fila in columnas:
            presentes[fila["table_name"]].add(fila["column_name"])
        if not aplicada or aplicada["sha256"] != esperada or any(
            not cols <= presentes[tabla] for tabla, cols in requeridas.items()
        ):
            raise RuntimeError("El esquema PostgreSQL no coincide con las migraciones de este proyecto.")

    def adquirir_instancia(self):
        if self._instancia is not None:
            raise RuntimeError("Esta instancia ya mantiene el bloqueo de la cola.")
        db = self._conectar(autocommit=True)
        try:
            self._tiempos(db, local=False)
            if not db.execute("SELECT pg_try_advisory_lock(%s) AS ok", (DB_LOCK_KEY,)).fetchone()["ok"]:
                raise RuntimeError("Otro backend o mantenimiento está usando esta base de StockEye.")
        except BaseException:
            db.close()
            raise
        self._instancia = db

    def verificar_instancia(self):
        db = self._instancia
        if db is None or db.closed:
            raise InstanciaPerdida("Se perdió la sesión de exclusión PostgreSQL; reinicie el backend.")
        try:
            row = db.execute(
                "SELECT EXISTS (SELECT 1 FROM pg_locks WHERE locktype='advisory' "
                "AND pid=pg_backend_pid() AND granted AND classid=%s::oid "
                "AND objid=%s::oid AND objsubid=1) AS vigente",
                (DB_LOCK_KEY >> 32, DB_LOCK_KEY & 0xFFFFFFFF),
            ).fetchone()
        except psycopg.Error as error:
            raise InstanciaPerdida("Se perdió la sesión de exclusión PostgreSQL; reinicie el backend.") from error
        if not row["vigente"]:
            raise InstanciaPerdida("Se perdió el bloqueo PostgreSQL; reinicie el backend.")

    def liberar_instancia(self):
        db, self._instancia = self._instancia, None
        if db is None:
            return
        try:
            if not db.closed:
                db.execute("SELECT pg_advisory_unlock(%s)", (DB_LOCK_KEY,))
        except psycopg.Error:
            pass
        finally:
            db.close()

    def estable(self, sucursal: int, relativo: str, firma: str,
                tiempo: float, espera: float) -> bool:
        with self.conexion() as db:
            anterior = db.execute(
                "SELECT * FROM public.observaciones WHERE sucursal_id=%s AND relativo=%s FOR UPDATE",
                (sucursal, relativo),
            ).fetchone()
            if anterior is None or anterior["firma"] != firma:
                db.execute(
                    "INSERT INTO public.observaciones "
                    "(sucursal_id,relativo,firma,visto_desde,registrado) VALUES (%s,%s,%s,%s,FALSE) "
                    "ON CONFLICT (sucursal_id,relativo) DO UPDATE SET firma=excluded.firma, "
                    "visto_desde=excluded.visto_desde,registrado=FALSE",
                    (sucursal, relativo, firma, tiempo),
                )
                return False
            return not anterior["registrado"] and tiempo - anterior["visto_desde"] >= espera

    def olvidar_ausentes(self, sucursal: int, presentes: set[str]):
        with self.conexion() as db:
            db.execute(
                "DELETE FROM public.observaciones WHERE sucursal_id=%s "
                "AND NOT (relativo=ANY(%s::text[]))", (sucursal, list(presentes)),
            )

    def encolar(self, *, ident: str, sucursal: int, relativo: str, sha256: str,
                copia: str | None, firma: str, error: str | None = None) -> bool:
        with self.conexion() as db:
            insertado = db.execute(
                "INSERT INTO public.trabajos "
                "(id,sucursal_id,relativo,nombre,sha256,copia,estado,creado_en,error,terminado_en) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING",
                (ident, sucursal, relativo, Path(relativo).name, sha256, copia,
                 "error" if error else "pendiente", ahora(), error, ahora() if error else None),
            ).rowcount == 1
            db.execute(
                "UPDATE public.observaciones SET registrado=TRUE "
                "WHERE sucursal_id=%s AND relativo=%s AND firma=%s",
                (sucursal, relativo, firma),
            )
            return insertado

    def recuperar_interrumpidos(self) -> int:
        self.verificar_instancia()
        with self.conexion() as db:
            return db.execute(
                "UPDATE public.trabajos SET estado='pendiente', iniciado_en=NULL WHERE estado='procesando'"
            ).rowcount

    def tomar(self) -> dict | None:
        with self.conexion() as db:
            fila = db.execute(
                "SELECT id FROM public.trabajos WHERE estado='pendiente' "
                "ORDER BY secuencia LIMIT 1 FOR UPDATE"
            ).fetchone()
            if fila is None:
                return None
            return db.execute(
                "UPDATE public.trabajos SET estado='procesando',iniciado_en=%s,"
                "intentos=intentos+1,error=NULL WHERE id=%s RETURNING *",
                (ahora(), fila["id"]),
            ).fetchone()

    def terminar(self, ident: str, error: str | None = None):
        with self.conexion() as db:
            db.execute(
                "UPDATE public.trabajos SET estado=%s,terminado_en=%s,error=%s WHERE id=%s",
                ("error" if error else "completada", ahora(), error, ident),
            )

    def obtener(self, ident: str) -> dict | None:
        with self.conexion() as db:
            return db.execute("SELECT * FROM public.trabajos WHERE id=%s", (ident,)).fetchone()

    def listar(self, sucursal=None, estado=None, limite=100, desde=0) -> tuple[list[dict], int]:
        condiciones, valores = [], []
        if sucursal is not None:
            condiciones.append("sucursal_id=%s")
            valores.append(sucursal)
        if estado is not None:
            condiciones.append("estado=%s")
            valores.append(estado)
        where = " WHERE " + " AND ".join(condiciones) if condiciones else ""
        with self.conexion() as db:
            total = db.execute(
                "SELECT COUNT(*) AS total FROM public.trabajos" + where, valores
            ).fetchone()["total"]
            filas = db.execute(
                "SELECT * FROM public.trabajos" + where + " ORDER BY secuencia DESC LIMIT %s OFFSET %s",
                [*valores, limite, desde],
            ).fetchall()
            return filas, total

    def conteos(self) -> dict:
        cuenta = dict.fromkeys(["pendiente", "procesando", "completada", "error"], 0)
        with self.conexion() as db:
            for fila in db.execute("SELECT estado,COUNT(*) AS n FROM public.trabajos GROUP BY estado"):
                cuenta[fila["estado"]] = fila["n"]
        return cuenta

    def reintentar_errores(self) -> int:
        self.verificar_instancia()
        with self.conexion() as db:
            return db.execute(
                "UPDATE public.trabajos SET estado='pendiente',error=NULL,iniciado_en=NULL,"
                "terminado_en=NULL WHERE estado='error' AND copia IS NOT NULL"
            ).rowcount
