"""Limita a localhost únicamente el servicio PostgreSQL 18 instalado para StockEye."""
from __future__ import annotations

import ctypes
import json
from pathlib import Path
import re
import subprocess
import time

HERE = Path(__file__).resolve().parent
RESULT = HERE / "solo-local-resultado.json"
PG_ROOT = Path(r"C:\Program Files\PostgreSQL\18")
CONFIG = PG_ROOT / "data" / "postgresql.conf"
SERVICE = "postgresql-x64-18"
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def restart_service():
    subprocess.run(
        ["powershell.exe", "-NoProfile", "-Command",
         "Restart-Service -Name 'postgresql-x64-18' -ErrorAction Stop"],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        creationflags=NO_WINDOW,
    )


def wait_ready():
    deadline = time.monotonic() + 25
    while time.monotonic() < deadline:
        result = subprocess.run(
            [str(PG_ROOT / "bin" / "pg_isready.exe"),
             "-h", "127.0.0.1", "-p", "5432", "-t", "2"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=NO_WINDOW,
        )
        if result.returncode == 0:
            return
        time.sleep(.25)
    raise RuntimeError("PostgreSQL no respondió en 127.0.0.1:5432 después del reinicio.")


def main():
    outcome = {"ok": False, "servicio": SERVICE, "direccion": "127.0.0.1", "puerto": 5432}
    original = None
    changed = False
    try:
        if not ctypes.windll.shell32.IsUserAnAdmin():
            raise RuntimeError("La configuración del servicio requiere el consentimiento administrativo de Windows.")
        if CONFIG.resolve().parent != (PG_ROOT / "data").resolve() or CONFIG.is_symlink():
            raise RuntimeError("La ruta de configuración no es la esperada.")
        auto = CONFIG.with_name("postgresql.auto.conf")
        if auto.exists() and re.search(r"(?m)^\s*listen_addresses\s*=", auto.read_text(encoding="utf-8")):
            raise RuntimeError("postgresql.auto.conf sobrescribe listen_addresses; revisar antes de modificar.")
        original = CONFIG.read_text(encoding="utf-8")
        pattern = r"(?m)^[ \t]*listen_addresses[ \t]*=.*$"
        lines = re.findall(pattern, original)
        if len(lines) != 1:
            raise RuntimeError("listen_addresses no tiene el formato único esperado.")
        if re.fullmatch(r"\s*listen_addresses\s*=\s*'127\.0\.0\.1'\s*(?:#.*)?", lines[0]):
            wait_ready()
            outcome.update(ok=True, ya_configurado=True)
        else:
            backup = CONFIG.with_name("postgresql.conf.stockeye-antes-local-20261114.bak")
            if backup.exists():
                raise RuntimeError("El respaldo de configuración ya existe; no se sobrescribirá.")
            with backup.open("x", encoding="utf-8", newline="") as handle:
                handle.write(original)
            updated = re.sub(pattern, "listen_addresses = '127.0.0.1'", original)
            CONFIG.write_text(updated, encoding="utf-8", newline="")
            changed = True
            restart_service()
            wait_ready()
            outcome.update(ok=True, respaldo=str(backup))
    except Exception as error:
        if changed and original is not None:
            try:
                CONFIG.write_text(original, encoding="utf-8", newline="")
                restart_service()
                outcome["configuracion_restaurada"] = True
            except Exception:
                outcome["configuracion_restaurada"] = False
        outcome["error"] = str(error)
    RESULT.write_text(json.dumps(outcome, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(outcome, ensure_ascii=False), flush=True)
    return 0 if outcome["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
