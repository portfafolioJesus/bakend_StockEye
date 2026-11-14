"""Migra la cola SQLite a PostgreSQL sin iniciar la API ni cargar el modelo."""
from __future__ import annotations

import argparse
from collections import Counter
from contextlib import closing, contextmanager
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sqlite3
import sys

from stockeye.configuracion import cargar_configuracion
from stockeye.instancia import InstanciaUnica

COLUMNAS = {
    "trabajos": ("secuencia", "id", "sucursal_id", "relativo", "nombre", "sha256",
                 "copia", "estado", "creado_en", "iniciado_en", "terminado_en", "intentos", "error"),
    "observaciones": ("sucursal_id", "relativo", "firma", "visto_desde", "registrado"),
}


class ErrorMigracion(RuntimeError):
    pass


def conectar_sqlite_lectura(ruta):
    ruta = Path(ruta).resolve()
    if not ruta.is_file():
        raise ErrorMigracion("No existe la SQLite de origen.")
    db = sqlite3.connect(ruta.as_uri() + "?mode=ro", uri=True, timeout=20)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA query_only=ON")
    return db


@contextmanager
def bloquear_origen(ruta):
    bloqueo = InstanciaUnica(Path(ruta).resolve().parent / "backend.lock")
    bloqueo.adquirir()
    try:
        yield
    finally:
        bloqueo.liberar()


def crear_snapshot(origen, destino):
    origen, destino = Path(origen).resolve(), Path(destino).resolve()
    if origen == destino or destino.exists():
        raise ErrorMigracion("El respaldo no puede reemplazar un archivo existente.")
    destino.parent.mkdir(parents=True, exist_ok=True)
    os.close(os.open(str(destino), os.O_CREAT | os.O_EXCL | os.O_WRONLY))
    with closing(conectar_sqlite_lectura(origen)) as fuente:
        with closing(sqlite3.connect(destino)) as copia:
            fuente.backup(copia, pages=256, sleep=.05)
            if [f[0] for f in copia.execute("PRAGMA quick_check")] != ["ok"]:
                raise ErrorMigracion("El respaldo no superó quick_check.")
    return destino


def leer_sqlite(ruta):
    with closing(conectar_sqlite_lectura(ruta)) as db:
        db.execute("BEGIN")
        if [f[0] for f in db.execute("PRAGMA quick_check")] != ["ok"]:
            raise ErrorMigracion("La SQLite no superó quick_check.")
        datos = {}
        for tabla, columnas in COLUMNAS.items():
            actuales = tuple(f[1] for f in db.execute(f"PRAGMA table_info({tabla})"))
            if actuales != columnas:
                raise ErrorMigracion(f"Esquema SQLite inesperado: {tabla}.")
            datos[tabla] = [dict(f) for f in db.execute(f"SELECT {', '.join(columnas)} FROM {tabla}")]
        contador = db.execute("SELECT seq FROM sqlite_sequence WHERE name='trabajos'").fetchone()
        datos["contador_sqlite"] = int(contador[0]) if contador else 0
        for fila in datos["trabajos"]:
            if not re.fullmatch(r"[0-9a-f]{32}", fila["id"]):
                raise ErrorMigracion("ID de trabajo incompatible.")
            if fila["estado"] not in {"pendiente", "procesando", "completada", "error"}:
                raise ErrorMigracion("Estado de trabajo desconocido.")
        for fila in datos["observaciones"]:
            if fila["registrado"] not in (0, 1) or not math.isfinite(fila["visto_desde"]):
                raise ErrorMigracion("Observación SQLite incompatible.")
            fila["registrado"] = bool(fila["registrado"])
        ordenar(datos)
        db.rollback()
        return datos


def ordenar(datos):
    datos["trabajos"].sort(key=lambda f: f["secuencia"])
    datos["observaciones"].sort(key=lambda f: (f["sucursal_id"], f["relativo"]))


def huella_filas(filas):
    raw = json.dumps(filas, ensure_ascii=False, sort_keys=True,
                     separators=(",", ":"), allow_nan=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()



def reubicar_copias(datos, cfg):
    """Repara referencias de una copia del proyecto; nunca mueve fotografías."""
    raiz = cfg.temporales.resolve()
    cambios = []
    for fila in datos["trabajos"]:
        if fila["estado"] not in {"pendiente", "procesando"} or not fila["copia"]:
            continue
        candidato = raiz / Path(fila["copia"]).name
        destino = candidato.resolve()
        if candidato.is_symlink() or destino.parent != raiz or not destino.is_file():
            raise ErrorMigracion("Falta una copia local activa en la carpeta temporal del destino.")
        huella = hashlib.sha256()
        with destino.open("rb") as handle:
            for bloque in iter(lambda: handle.read(1024 * 1024), b""):
                huella.update(bloque)
        if huella.hexdigest() != fila["sha256"]:
            raise ErrorMigracion("Una copia local activa no coincide con su SHA-256 registrado.")
        nueva = str(destino)
        if fila["copia"] != nueva:
            cambios.append({"id": fila["id"], "anterior": fila["copia"], "nueva": nueva})
            fila["copia"] = nueva
    return cambios

def resumen(datos):
    estados = Counter(f"S{f['sucursal_id']}:{f['estado']}" for f in datos["trabajos"])
    return {
        "trabajos": len(datos["trabajos"]), "observaciones": len(datos["observaciones"]),
        "por_sucursal_y_estado": dict(sorted(estados.items())),
        "huellas": {t: huella_filas(datos[t]) for t in COLUMNAS},
        "contador_sqlite": datos["contador_sqlite"],
    }


@contextmanager
def registro_postgres(cfg):
    from stockeye.registro import Registro
    opciones = cfg.base_datos
    registro = Registro(opciones.conexion_dsn(), connect_timeout=opciones.connect_timeout,
                        statement_timeout_ms=opciones.statement_timeout_ms)
    registro.adquirir_instancia()
    try:
        yield registro
    finally:
        registro.liberar_instancia()


def preparar_esquema(registro, carpeta):
    archivos = sorted(Path(carpeta).glob("*.sql"))
    if not archivos:
        raise ErrorMigracion("No hay migraciones SQL.")
    with registro.conexion() as db:
        db.execute("""
            CREATE TABLE IF NOT EXISTS public.schema_migrations (
                version TEXT PRIMARY KEY, sha256 TEXT NOT NULL,
                aplicado_en TIMESTAMPTZ NOT NULL DEFAULT now()
            )
        """)
        for archivo in archivos:
            nombre = re.fullmatch(r"(\d{3})_[a-z0-9_]+\.sql", archivo.name)
            if not nombre:
                raise ErrorMigracion("Nombre de migración no admitido.")
            version = nombre.group(1)
            raw = archivo.read_bytes()
            sha = hashlib.sha256(raw).hexdigest()
            aplicada = db.execute("SELECT sha256 FROM public.schema_migrations WHERE version=%s",
                                  (version,)).fetchone()
            if aplicada:
                if aplicada["sha256"] != sha:
                    raise ErrorMigracion(f"La migración {version} aplicada fue modificada.")
                continue
            db.execute(raw.decode("utf-8-sig"))
            db.execute("INSERT INTO public.schema_migrations(version,sha256) VALUES(%s,%s)",
                       (version, sha))


def leer_postgres(db):
    datos = {tabla: [dict(f) for f in db.execute(
        f"SELECT {', '.join(columnas)} FROM public.{tabla}").fetchall()]
        for tabla, columnas in COLUMNAS.items()}
    ordenar(datos)
    return datos


def comprobar_filas(esperado, actual):
    for tabla in COLUMNAS:
        if len(esperado[tabla]) != len(actual[tabla]) or huella_filas(esperado[tabla]) != huella_filas(actual[tabla]):
            raise ErrorMigracion(f"El contenido completo de {tabla} no coincide.")


def importar(registro, datos):
    registro.comprobar_version_esquema()
    with registro.conexion() as db:
        db.execute("LOCK TABLE public.trabajos,public.observaciones IN ACCESS EXCLUSIVE MODE")
        for tabla in COLUMNAS:
            if db.execute(f"SELECT COUNT(*) AS n FROM public.{tabla}").fetchone()["n"]:
                raise ErrorMigracion(f"El destino {tabla} no está vacío; no se sobrescribirá.")
        with db.cursor() as cursor:
            for tabla, columnas in COLUMNAS.items():
                if datos[tabla]:
                    placeholders = ", ".join(["%s"] * len(columnas))
                    override = " OVERRIDING SYSTEM VALUE" if tabla == "trabajos" else ""
                    cursor.executemany(
                        f"INSERT INTO public.{tabla} ({', '.join(columnas)}){override} VALUES ({placeholders})",
                        [tuple(f[c] for c in columnas) for f in datos[tabla]],
                    )
        comprobar_filas(datos, leer_postgres(db))
        siguiente = max([datos["contador_sqlite"], 0] + [f["secuencia"] for f in datos["trabajos"]]) + 1
        if siguiente > 2**63 - 1:
            raise ErrorMigracion("Secuencia fuera de rango.")
        db.execute(f"ALTER TABLE public.trabajos ALTER COLUMN secuencia RESTART WITH {siguiente}")


def verificar(registro, datos):
    registro.comprobar_version_esquema()
    with registro.conexion() as db:
        db.execute("LOCK TABLE public.trabajos,public.observaciones IN SHARE MODE")
        comprobar_filas(datos, leer_postgres(db))


def ejecutar(args):
    cfg = cargar_configuracion(args.config)
    origen = (args.sqlite or cfg.datos / "cola.sqlite3").resolve()
    if args.inventario:
        datos = leer_sqlite(origen)
        cambios = reubicar_copias(datos, cfg) if args.reubicar_copias else []
        print(json.dumps({**resumen(datos), "cantidad_reubicaciones": len(cambios),
                          "reubicaciones": cambios}, indent=2))
        return
    if args.snapshot:
        if args.respaldo is None:
            raise ErrorMigracion("--snapshot necesita --respaldo.")
        with bloquear_origen(origen):
            copia = crear_snapshot(origen, args.respaldo)
        print(json.dumps({"snapshot": str(copia), "inventario": resumen(leer_sqlite(copia))}, indent=2))
        return
    if args.preparar_esquema:
        with registro_postgres(cfg) as registro:
            preparar_esquema(registro, Path(__file__).resolve().parent / "migraciones")
        print("Esquema preparado; huellas de migraciones verificadas.")
        return
    with bloquear_origen(origen):
        with registro_postgres(cfg) as registro:
            if args.importar:
                if args.respaldo is None:
                    raise ErrorMigracion("--importar necesita --respaldo.")
                copia = crear_snapshot(origen, args.respaldo)
                datos = leer_sqlite(copia)
                cambios = reubicar_copias(datos, cfg) if args.reubicar_copias else []
                importar(registro, datos)
            else:
                datos = leer_sqlite(origen)
                cambios = reubicar_copias(datos, cfg) if args.reubicar_copias else []
                verificar(registro, datos)
    print(json.dumps({"resultado": "importado" if args.importar else "verificado",
                      "inventario": resumen(datos), "cantidad_reubicaciones": len(cambios),
                      "reubicaciones": cambios}, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path(__file__).with_name("config.json"))
    parser.add_argument("--sqlite", type=Path)
    parser.add_argument("--respaldo", type=Path)
    parser.add_argument("--reubicar-copias", action="store_true",
                        help="Reubica referencias activas solo si el archivo local y su SHA-256 coinciden.")
    grupo = parser.add_mutually_exclusive_group(required=True)
    for opcion in ("inventario", "snapshot", "preparar-esquema", "importar", "verificar"):
        grupo.add_argument("--" + opcion, action="store_true")
    args = parser.parse_args()
    try:
        ejecutar(args)
        return 0
    except ErrorMigracion as error:
        print(f"Migración no completada: {error}", file=sys.stderr)
    except Exception as error:
        codigo = getattr(error, "sqlstate", None)
        detalle = f"; SQLSTATE={codigo}" if codigo else ""
        print(f"Migración no completada ({type(error).__name__}{detalle}). "
              "Revise conexión, permisos y configuración; no se imprimen credenciales.",
              file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
