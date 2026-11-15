"""Punto de entrada único. Cada contenedor corre un subcomando:

    python -m stockeye.cli api             API FastAPI (uvicorn)
    python -m stockeye.cli worker          microservicio de inferencia
    python -m stockeye.cli notificador     microservicio de push (FCM + Web Push)
    python -m stockeye.cli ia              microservicio de IA de producto (Groq)
    python -m stockeye.cli importador      fotos dejadas en entradas/<RECINTO>/<GÓNDOLA>/
    python -m stockeye.cli db migrar|estado|seed
    python -m stockeye.cli modelo registrar modelos/x.json --activar | modelo listar
    python -m stockeye.cli usuario crear --email ... --rol ADMINISTRADOR
    python -m stockeye.cli vapid           genera claves Web Push
    python -m stockeye.cli demo imagenes   genera fotos de ejemplo para el seed
"""
from __future__ import annotations

import argparse
import base64
import getpass
import json
import logging
import sys
import time
from pathlib import Path

import psycopg

from .core import migraciones
from .core.config import ajustes


def _logs() -> None:
    logging.basicConfig(level=logging.INFO, stream=sys.stdout,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def esperar_db(dsn: str, segundos: int = 60) -> None:
    limite = time.monotonic() + segundos
    while True:
        try:
            with psycopg.connect(dsn, connect_timeout=3) as c:
                c.execute("SELECT 1")
            return
        except psycopg.OperationalError as e:
            if time.monotonic() > limite:
                raise SystemExit(f"La base de datos no responde: {e}")
            time.sleep(2)


def cmd_api(args) -> None:
    import uvicorn
    uvicorn.run("stockeye.api.main:app", host=args.host, port=args.port, workers=args.workers,
                proxy_headers=True, forwarded_allow_ips="*", log_level="info")


def cmd_worker(_) -> None:
    from .inferencia.worker import WorkerInferencia
    a = ajustes()
    esperar_db(a.database_url)
    WorkerInferencia(a).correr()


def cmd_notificador(_) -> None:
    from .notificador.servicio import Notificador
    a = ajustes()
    esperar_db(a.database_url)
    Notificador(a).correr()


def cmd_ia(_) -> None:
    from .ia.servicio import EnriquecedorIA
    a = ajustes()
    esperar_db(a.database_url)
    EnriquecedorIA(a).correr()


def cmd_importador(_) -> None:
    from .importador.servicio import Importador
    a = ajustes()
    esperar_db(a.database_url)
    Importador(a).correr()


def cmd_db(args) -> None:
    a = ajustes()
    esperar_db(a.database_url)
    if args.accion == "migrar":
        hechas = migraciones.aplicar(a.database_url, a.db_dir)
        print("Migraciones aplicadas:", ", ".join(hechas) if hechas else "ninguna (al día)")
    elif args.accion == "estado":
        for m in migraciones.estado(a.database_url, a.db_dir):
            print(f"{m['archivo']:<35} {m['estado']:<10} {m['aplicada_en'] or ''}")
    elif args.accion == "seed":
        migraciones.aplicar(a.database_url, a.db_dir)
        if migraciones.sembrar_demo(a.database_url, a.db_dir, args.forzar):
            print("Datos de demo cargados. Usuarios: admin@stockeye.test, cmunoz@stockeye.test, dsoto@stockeye.test …"
                  " · clave: StockEye2026!")


def cmd_modelo(args) -> None:
    from .inferencia.registro import SQL_ACTIVAR, SQL_REGISTRAR, parametros_sql
    a = ajustes()
    with psycopg.connect(a.database_url) as c:
        if args.accion == "listar":
            for f in c.execute("""SELECT id, nombre, version, familia, ruta_pesos, umbral_confianza, activo
                                    FROM modelo_ia ORDER BY id""").fetchall():
                print(*f, sep="\t")
            return
        manifiesto = Path(args.manifiesto)
        m = json.loads(manifiesto.read_text(encoding="utf-8"))
        onnx = manifiesto.parent / m["archivo"]
        if not onnx.is_file():
            raise SystemExit(f"No existe {onnx}")
        if manifiesto.parent.resolve() != a.modelos_dir.resolve():
            print(f"Aviso: el worker busca los pesos en {a.modelos_dir}; copia {onnx.name} ahí.")
        modelo_id = c.execute(SQL_REGISTRAR, parametros_sql(m, f"modelos/{m['archivo']}")).fetchone()[0]
        print(f"Modelo registrado: id={modelo_id} {m['nombre']} {m['version']}")
        if args.activar:
            c.execute(SQL_ACTIVAR, {"id": modelo_id, "usuario": None})
            print("Activado: los workers lo recargan automáticamente.")


def cmd_usuario(args) -> None:
    from .core.seguridad import hash_clave
    a = ajustes()
    clave = args.clave or getpass.getpass("Clave: ")
    with psycopg.connect(a.database_url) as c:
        uid = c.execute("""INSERT INTO usuario (nombre, apellido, email, password_hash, rol)
                           VALUES (%s, %s, %s, %s, %s) RETURNING id""",
                        [args.nombre, args.apellido, args.email.lower(), hash_clave(clave), args.rol]).fetchone()[0]
        for codigo in args.recinto or []:
            c.execute("""INSERT INTO usuario_recinto (usuario_id, recinto_id)
                         SELECT %s, id FROM recinto WHERE codigo = %s""", [uid, codigo])
    print(f"Usuario creado (id {uid})")


def cmd_vapid(_) -> None:
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    clave = ec.generate_private_key(ec.SECP256R1())
    privada = clave.private_numbers().private_value.to_bytes(32, "big")
    publica = clave.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    b64 = lambda b: base64.urlsafe_b64encode(b).decode().rstrip("=")  # noqa: E731
    print("# Copia estas líneas en tu .env (la privada es secreta)")
    print(f"VAPID_PUBLICA={b64(publica)}")
    print(f"VAPID_PRIVADA={b64(privada)}")


def cmd_demo(_) -> None:
    """Dibuja fotos de góndola para las imágenes del seed (sin fotos reales)."""
    import cv2
    import numpy as np
    from .core.almacenamiento import almacenamiento, ruta_anotada
    from .inferencia.motor import Region
    from .inferencia.postproceso import anotar
    a = ajustes()
    rng = np.random.default_rng(7)
    colores = [(215, 222, 232), (175, 210, 150), (0, 157, 236), (229, 234, 240), (136, 136, 0), (20, 108, 200)]
    with psycopg.connect(a.database_url) as c:
        filas = c.execute("""SELECT i.id, i.ruta_archivo, p.id AS pid FROM imagen i
                               LEFT JOIN prediccion p ON p.imagen_id = i.id""").fetchall()
        creadas = 0
        for img_id, ruta, pid in filas:
            if almacenamiento().existe(ruta):
                continue
            alto, ancho = 720, 1280
            lienzo = np.full((alto, ancho, 3), (70, 62, 55), np.uint8)
            cajas = c.execute("SELECT x_min, y_min, x_max, y_max, confianza FROM deteccion WHERE prediccion_id = %s",
                              [pid]).fetchall() if pid else []
            for fila in range(3):
                y0 = 60 + fila * 220
                x = 40
                while x < ancho - 60:
                    w = int(rng.integers(55, 80))
                    cv2.rectangle(lienzo, (x, y0 + int(rng.integers(0, 30))), (x + w - 6, y0 + 170),
                                  colores[int(rng.integers(0, len(colores)))], -1)
                    x += w
                cv2.rectangle(lienzo, (20, y0 + 172), (ancho - 20, y0 + 186), (205, 200, 196), -1)
            for x0, y0, x1, y1, _ in cajas:
                cv2.rectangle(lienzo, (int(x0 * ancho), int(y0 * alto)), (int(x1 * ancho), int(y1 * alto)), (70, 62, 55), -1)
            _, buf = cv2.imencode(".jpg", lienzo, [cv2.IMWRITE_JPEG_QUALITY, 88])
            almacenamiento().guardar(ruta, buf.tobytes())
            regiones = [Region("vacio", float(conf), float(x0), float(y0), float(x1), float(y1)) for x0, y0, x1, y1, conf in cajas]
            almacenamiento().guardar(ruta_anotada(ruta), anotar(lienzo, np.zeros((alto, ancho), bool), regiones))
            creadas += 1
    print(f"{creadas} fotos de demo creadas en {a.datos_dir}")


def main(argv: list[str] | None = None) -> None:
    _logs()
    p = argparse.ArgumentParser(prog="stockeye", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="comando", required=True)
    s = sub.add_parser("api"); s.add_argument("--host", default="0.0.0.0"); s.add_argument("--port", type=int, default=8000)
    s.add_argument("--workers", type=int, default=1); s.set_defaults(f=cmd_api)
    sub.add_parser("worker").set_defaults(f=cmd_worker)
    sub.add_parser("notificador").set_defaults(f=cmd_notificador)
    sub.add_parser("ia").set_defaults(f=cmd_ia)
    sub.add_parser("importador").set_defaults(f=cmd_importador)
    s = sub.add_parser("db"); s.add_argument("accion", choices=["migrar", "estado", "seed"])
    s.add_argument("--forzar", action="store_true"); s.set_defaults(f=cmd_db)
    s = sub.add_parser("modelo"); s.add_argument("accion", choices=["registrar", "listar"])
    s.add_argument("manifiesto", nargs="?"); s.add_argument("--activar", action="store_true"); s.set_defaults(f=cmd_modelo)
    s = sub.add_parser("usuario"); s.add_argument("accion", choices=["crear"])
    s.add_argument("--email", required=True); s.add_argument("--nombre", required=True)
    s.add_argument("--apellido", required=True)
    s.add_argument("--rol", required=True, choices=["ADMINISTRADOR", "SUPERVISOR", "REPONEDOR"])
    s.add_argument("--recinto", action="append", help="código, se puede repetir"); s.add_argument("--clave")
    s.set_defaults(f=cmd_usuario)
    sub.add_parser("vapid").set_defaults(f=cmd_vapid)
    s = sub.add_parser("demo"); s.add_argument("accion", choices=["imagenes"]); s.set_defaults(f=cmd_demo)
    args = p.parse_args(argv)
    if args.comando == "modelo" and args.accion == "registrar" and not args.manifiesto:
        p.error("indica el manifiesto .json")
    args.f(args)


if __name__ == "__main__":
    main()
