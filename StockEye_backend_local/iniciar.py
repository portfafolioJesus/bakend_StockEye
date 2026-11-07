"""Punto de entrada: python iniciar.py --config config.json"""
from pathlib import Path
import argparse
import logging

from stockeye.configuracion import cargar_configuracion


def main():
    parser = argparse.ArgumentParser(description="StockEye: revisor cada 30 s, cola local y API.")
    parser.add_argument("--config", default=str(Path(__file__).with_name("config.json")))
    parser.add_argument("--comprobar-modelo", action="store_true", help="Carga y verifica el .pt sin iniciar servidor ni procesar imágenes.")
    args = parser.parse_args()
    cfg = cargar_configuracion(args.config)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    if args.comprobar_modelo:
        from stockeye.motor import MotorSegFormer
        motor = MotorSegFormer(cfg)
        print(f"Modelo compatible: {motor.version} | dispositivo={motor.dispositivo} | operación={motor.operacion}")
        return
    import uvicorn
    from stockeye.api import crear_app
    print(f"StockEye: http://{cfg.api.host}:{cfg.api.puerto}/docs")
    print("El revisor confirma cada archivo en dos revisiones; después se procesa uno por uno.")
    print("Para cerrar: Ctrl+C. Se espera la fotografía en curso.")
    uvicorn.run(crear_app(cfg), host=cfg.api.host, port=cfg.api.puerto, workers=1)


if __name__ == "__main__":
    main()
