"""Prueba de carga: ¿una ráfaga de un recinto frena a los otros?

Sube N fotos de golpe a R01 y unas pocas a R02 (con las API keys de demo) y
mide cuánto esperó cada foto hasta quedar PROCESADA. Con turnos por recinto,
las de R02 deben terminar en segundos aunque R01 tenga la cola llena.

    python herramientas/simular_camaras.py --api http://localhost:8080 --rafaga 40 --otras 3
"""
from __future__ import annotations

import argparse
import statistics
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).parent))
from empaquetar_modelo import imagen_sintetica  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--api", default="http://localhost:8080")
    ap.add_argument("--rafaga", type=int, default=40, help="fotos de R01 (ráfaga)")
    ap.add_argument("--otras", type=int, default=3, help="fotos de R02")
    ap.add_argument("--admin", default="admin@stockeye.test")
    ap.add_argument("--clave", default="StockEye2026!")
    a = ap.parse_args()
    base = a.api.rstrip("/") + "/api/v1"
    jpg = imagen_sintetica(1920, 1080)
    c = httpx.Client(timeout=60)
    token = c.post(f"{base}/auth/login", json={"email": a.admin, "clave": a.clave}).json()["acceso"]
    admin = {"Authorization": f"Bearer {token}"}

    def subir(camara: str) -> tuple[str, int, float]:
        r = c.post(f"{base}/ingesta", headers={"X-API-Key": f"demo-{camara}"}, files={"foto": ("f.jpg", jpg, "image/jpeg")})
        r.raise_for_status()
        return camara[:3], r.json()["imagen_id"], time.monotonic()

    trabajos = ["R01-CAM04"] * a.rafaga + ["R02-CAM01"] * a.otras     # la ráfaga se encola PRIMERO
    print(f"Subiendo {a.rafaga} fotos de R01 y luego {a.otras} de R02…")
    with ThreadPoolExecutor(8) as ex:
        subidas = list(ex.map(subir, trabajos))
    pendientes = {i: (rec, t) for rec, i, t in subidas}
    esperas: dict[str, list[float]] = {"R01": [], "R02": []}
    inicio = time.monotonic()
    while pendientes and time.monotonic() - inicio < 900:
        for i, (rec, t) in list(pendientes.items()):
            estado = c.get(f"{base}/imagenes/{i}", headers=admin).json()["estado"]
            if estado in ("PROCESADA", "ERROR"):
                esperas[rec].append(time.monotonic() - t)
                del pendientes[i]
        time.sleep(0.5)
    for rec, v in esperas.items():
        if v:
            v.sort()
            print(f"{rec}: {len(v)} fotos · espera mediana {statistics.median(v):.1f} s · máx. {v[-1]:.1f} s")
    print("Workers:", c.get(f"{base}/admin/cola", headers=admin).json()["workers"])


if __name__ == "__main__":
    main()
