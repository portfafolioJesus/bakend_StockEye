"""Aplica db/migraciones/NNN_*.sql en orden y registra su hash.

Una migración aplicada no se edita: si su hash cambia, se detiene con error.
Los cambios nuevos van en un archivo NNN+1.
"""
from __future__ import annotations

import hashlib
import logging
from pathlib import Path

import psycopg

log = logging.getLogger(__name__)

TABLA = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version     VARCHAR(10)  PRIMARY KEY,
    nombre      VARCHAR(200) NOT NULL,
    sha256      CHAR(64)     NOT NULL,
    aplicada_en TIMESTAMPTZ  NOT NULL DEFAULT now()
)"""
CANDADO = 727_001   # pg_advisory_lock: dos réplicas de la api no migran a la vez


def archivos(carpeta: Path) -> list[Path]:
    return sorted(p for p in (carpeta / "migraciones").glob("[0-9][0-9][0-9]_*.sql"))


def aplicar(dsn: str, carpeta: Path) -> list[str]:
    aplicadas: list[str] = []
    with psycopg.connect(dsn, autocommit=True) as conn:
        conn.execute("SELECT pg_advisory_lock(%s)", [CANDADO])
        try:
            conn.execute(TABLA)
            hechas = {v: s for v, s in conn.execute("SELECT version, sha256 FROM schema_migrations").fetchall()}
            for ruta in archivos(carpeta):
                version = ruta.name[:3]
                contenido = ruta.read_bytes()
                sha = hashlib.sha256(contenido).hexdigest()
                if version in hechas:
                    if hechas[version] != sha:
                        raise RuntimeError(f"La migración {ruta.name} cambió después de aplicarse. "
                                           "No edites migraciones aplicadas: crea una nueva.")
                    continue
                log.info("Aplicando migración %s", ruta.name)
                # Cada archivo trae su propio BEGIN/COMMIT.
                conn.execute(contenido.decode("utf-8"))
                conn.execute("INSERT INTO schema_migrations (version, nombre, sha256) VALUES (%s, %s, %s)",
                             [version, ruta.name, sha])
                aplicadas.append(ruta.name)
        finally:
            conn.execute("SELECT pg_advisory_unlock(%s)", [CANDADO])
    return aplicadas


def estado(dsn: str, carpeta: Path) -> list[dict]:
    with psycopg.connect(dsn, autocommit=True) as conn:
        conn.execute(TABLA)
        hechas = {v: (n, s, f) for v, n, s, f in conn.execute(
            "SELECT version, nombre, sha256, aplicada_en FROM schema_migrations").fetchall()}
    salida = []
    for ruta in archivos(carpeta):
        v = ruta.name[:3]
        sha = hashlib.sha256(ruta.read_bytes()).hexdigest()
        if v in hechas:
            salida.append(dict(archivo=ruta.name, estado="aplicada" if hechas[v][1] == sha else "MODIFICADA",
                               aplicada_en=hechas[v][2]))
        else:
            salida.append(dict(archivo=ruta.name, estado="pendiente", aplicada_en=None))
    return salida


def sembrar_demo(dsn: str, carpeta: Path, forzar: bool = False) -> bool:
    """Carga db/seed/seed_demo.sql solo si la BD no tiene recintos."""
    with psycopg.connect(dsn, autocommit=True) as conn:
        hay = conn.execute("SELECT EXISTS (SELECT 1 FROM recinto)").fetchone()[0]
        if hay and not forzar:
            log.info("La BD ya tiene datos; no se carga el seed de demo")
            return False
        conn.execute((carpeta / "seed" / "seed_demo.sql").read_text(encoding="utf-8"))
    return True
