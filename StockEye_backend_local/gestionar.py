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
    registro = None
    try:
        opciones = cfg.base_datos
        registro = Registro(
            opciones.conexion_dsn(), connect_timeout=opciones.connect_timeout,
            statement_timeout_ms=opciones.statement_timeout_ms,
        )
        registro.adquirir_instancia()
        registro.comprobar_version_esquema()
        if args.accion == "reintentar-errores":
            print("Trabajos devueltos a la cola:", registro.reintentar_errores())
        print(json.dumps(registro.conteos(), ensure_ascii=False, indent=2))
    finally:
        if registro is not None:
            registro.liberar_instancia()
        bloqueo.liberar()


if __name__ == "__main__":
    main()
