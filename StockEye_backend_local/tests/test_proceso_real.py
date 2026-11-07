"""Prueba HTTP contra iniciar.py en otro proceso, con SegFormer de prueba y CPU."""
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import time

import httpx

from preparar_modelo import preparar
from .conftest import foto
from .test_modelo import checkpoint  # Fixture que genera pesos de prueba, no entrenados.


def test_comando_real_revisa_procesa_y_sirve_por_http(cfg, checkpoint, tmp_path):
    preparar(checkpoint, cfg.modelo.archivo, modo="completa", umbral=.5)
    cfg.revision_segundos = 1
    cfg.estabilidad_segundos = 0
    cfg.modelo.dispositivo = "cpu"
    with socket.socket() as libre:
        libre.bind(("127.0.0.1", 0)); cfg.api.puerto = libre.getsockname()[1]
    archivo = tmp_path / "config.json"
    archivo.write_text(json.dumps(cfg.model_dump(mode="json")), encoding="utf-8")
    for n in (1, 2): foto(cfg.carpetas[n] / "foto.png")
    proyecto = Path(__file__).resolve().parents[1]
    log_path = tmp_path / "servidor.log"
    with log_path.open("w", encoding="utf-8") as log:
        proceso = subprocess.Popen([sys.executable, "iniciar.py", "--config", str(archivo)], cwd=proyecto,
            stdout=log, stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0,
            env={**os.environ, "HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1"})
        try:
            base = f"http://127.0.0.1:{cfg.api.puerto}"
            limite = time.monotonic() + 30
            with httpx.Client(base_url=base, trust_env=False, timeout=2) as cliente:
                while time.monotonic() < limite:
                    if proceso.poll() is not None:
                        raise AssertionError(log_path.read_text())
                    try:
                        salud = cliente.get("/health").json()
                        if salud["cola"]["completada"] == 2: break
                    except (httpx.HTTPError, ValueError): pass
                    time.sleep(.05)
                else: raise AssertionError(log_path.read_text())
                assert salud["modelo"]["disponible"]
                for n in (1, 2):
                    listado = cliente.get("/api/imagenes", params={"sucursal_id": n}).json()
                    assert len(listado) == 1 and listado[0]["sucursal_id"] == n
                    assert cliente.get(listado[0]["imagenUrl"]).headers["content-type"].startswith("image/jpeg")
                    d = cliente.get("/api/analisis/" + listado[0]["id"]).json()
                    assert d["gondolas"][0]["pct_vacio_observado"] == 100
                assert cliente.get("/docs").status_code == 200
        finally:
            if proceso.poll() is None:
                proceso.send_signal(signal.CTRL_BREAK_EVENT if os.name == "nt" else signal.SIGINT)
                try: proceso.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    proceso.kill(); proceso.wait()
        assert proceso.returncode == 0, log_path.read_text()
