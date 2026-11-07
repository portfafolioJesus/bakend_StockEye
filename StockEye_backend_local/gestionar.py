"""Operaciones locales sobre la cola. Ejecutar con el backend detenido."""
from pathlib import Path
import argparse
import json

from stockeye.configuracion import cargar_configuracion
from stockeye.instancia import InstanciaUnica
from stockeye.registro import Registro


def main():
    parser = argparse.ArgumentParser(description="Consultar o reintentar trabajos locales de StockEye.")
    parser.add_argument("accion", choices=["estado", "reintentar-errores"])
    parser.add_argument("--config", default=str(Path(__file__).with_name("config.json")))
    args = parser.parse_args()
    cfg = cargar_configuracion(args.config)
    cfg.crear_carpetas()
    bloqueo = InstanciaUnica(cfg.datos / "backend.lock")
    bloqueo.adquirir()
    try:
        registro = Registro(cfg.datos / "cola.sqlite3")
        if args.accion == "reintentar-errores":
            print("Trabajos devueltos a la cola:", registro.reintentar_errores())
        print(json.dumps(registro.conteos(), ensure_ascii=False, indent=2))
    finally:
        bloqueo.liberar()


if __name__ == "__main__":
    main()
