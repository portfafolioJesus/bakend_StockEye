from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
import sqlite3


def ahora() -> str:
    return datetime.now(timezone.utc).isoformat()


class Registro:
    """Cola FIFO persistente. Una conexión corta por operación y por hilo."""

    def __init__(self, ruta: Path):
        self.ruta = Path(ruta)
        self.ruta.parent.mkdir(parents=True, exist_ok=True)
        with self.conexion() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.executescript("""
                CREATE TABLE IF NOT EXISTS trabajos (
                    secuencia INTEGER PRIMARY KEY AUTOINCREMENT,
                    id TEXT NOT NULL UNIQUE,
                    sucursal_id INTEGER NOT NULL CHECK(sucursal_id IN (1, 2)),
                    relativo TEXT NOT NULL,
                    nombre TEXT NOT NULL,
                    sha256 TEXT NOT NULL,
                    copia TEXT,
                    estado TEXT NOT NULL CHECK(estado IN ('pendiente','procesando','completada','error')),
                    creado_en TEXT NOT NULL,
                    iniciado_en TEXT,
                    terminado_en TEXT,
                    intentos INTEGER NOT NULL DEFAULT 0,
                    error TEXT,
                    UNIQUE(sucursal_id, relativo, sha256)
                );
                CREATE INDEX IF NOT EXISTS cola_estado ON trabajos(estado, secuencia);
                CREATE TABLE IF NOT EXISTS observaciones (
                    sucursal_id INTEGER NOT NULL,
                    relativo TEXT NOT NULL,
                    firma TEXT NOT NULL,
                    visto_desde REAL NOT NULL,
                    registrado INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY(sucursal_id, relativo)
                );
            """)

    @contextmanager
    def conexion(self):
        db = sqlite3.connect(self.ruta, timeout=20)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA busy_timeout=20000")
        try:
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def estable(self, sucursal: int, relativo: str, firma: str,
                tiempo: float, espera: float) -> bool:
        with self.conexion() as db:
            anterior = db.execute("SELECT * FROM observaciones WHERE sucursal_id=? AND relativo=?",
                                  (sucursal, relativo)).fetchone()
            if anterior is None or anterior["firma"] != firma:
                db.execute("""INSERT INTO observaciones VALUES (?, ?, ?, ?, 0)
                    ON CONFLICT(sucursal_id, relativo) DO UPDATE SET
                    firma=excluded.firma, visto_desde=excluded.visto_desde, registrado=0""",
                           (sucursal, relativo, firma, tiempo))
                return False
            return not anterior["registrado"] and tiempo - anterior["visto_desde"] >= espera

    def olvidar_ausentes(self, sucursal: int, presentes: set[str]):
        with self.conexion() as db:
            guardadas = db.execute("SELECT relativo FROM observaciones WHERE sucursal_id=?", (sucursal,)).fetchall()
            db.executemany("DELETE FROM observaciones WHERE sucursal_id=? AND relativo=?",
                           [(sucursal, x["relativo"]) for x in guardadas if x["relativo"] not in presentes])

    def encolar(self, *, ident: str, sucursal: int, relativo: str, sha256: str,
                copia: str | None, firma: str, error: str | None = None) -> bool:
        with self.conexion() as db:
            cursor = db.execute("""INSERT OR IGNORE INTO trabajos
                (id,sucursal_id,relativo,nombre,sha256,copia,estado,creado_en,error,terminado_en)
                VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (ident, sucursal, relativo, Path(relativo).name, sha256, copia,
                 "error" if error else "pendiente", ahora(), error, ahora() if error else None))
            db.execute("UPDATE observaciones SET registrado=1 WHERE sucursal_id=? AND relativo=? AND firma=?",
                       (sucursal, relativo, firma))
            return cursor.rowcount == 1

    def recuperar_interrumpidos(self) -> int:
        with self.conexion() as db:
            return db.execute("UPDATE trabajos SET estado='pendiente', iniciado_en=NULL WHERE estado='procesando'").rowcount

    def tomar(self) -> dict | None:
        with self.conexion() as db:
            db.execute("BEGIN IMMEDIATE")
            fila = db.execute("SELECT * FROM trabajos WHERE estado='pendiente' ORDER BY secuencia LIMIT 1").fetchone()
            if fila is None:
                return None
            db.execute("UPDATE trabajos SET estado='procesando', iniciado_en=?, intentos=intentos+1, error=NULL WHERE id=?",
                       (ahora(), fila["id"]))
            return dict(db.execute("SELECT * FROM trabajos WHERE id=?", (fila["id"],)).fetchone())

    def terminar(self, ident: str, error: str | None = None):
        with self.conexion() as db:
            db.execute("UPDATE trabajos SET estado=?, terminado_en=?, error=? WHERE id=?",
                       ("error" if error else "completada", ahora(), error, ident))

    def obtener(self, ident: str) -> dict | None:
        with self.conexion() as db:
            fila = db.execute("SELECT * FROM trabajos WHERE id=?", (ident,)).fetchone()
            return dict(fila) if fila else None

    def listar(self, sucursal=None, estado=None, limite=100, desde=0) -> tuple[list[dict], int]:
        condiciones, valores = [], []
        if sucursal is not None:
            condiciones.append("sucursal_id=?"); valores.append(sucursal)
        if estado is not None:
            condiciones.append("estado=?"); valores.append(estado)
        where = " WHERE " + " AND ".join(condiciones) if condiciones else ""
        with self.conexion() as db:
            total = db.execute("SELECT COUNT(*) FROM trabajos" + where, valores).fetchone()[0]
            filas = db.execute("SELECT * FROM trabajos" + where + " ORDER BY secuencia DESC LIMIT ? OFFSET ?",
                               [*valores, limite, desde]).fetchall()
            return [dict(f) for f in filas], total

    def conteos(self) -> dict:
        cuenta = dict.fromkeys(["pendiente", "procesando", "completada", "error"], 0)
        with self.conexion() as db:
            for fila in db.execute("SELECT estado, COUNT(*) AS n FROM trabajos GROUP BY estado"):
                cuenta[fila["estado"]] = fila["n"]
        return cuenta

    def reintentar_errores(self) -> int:
        with self.conexion() as db:
            return db.execute("""UPDATE trabajos SET estado='pendiente', error=NULL, iniciado_en=NULL,
                terminado_en=NULL WHERE estado='error' AND copia IS NOT NULL""").rowcount
