"""Capturador de StockEye: corre en un mini PC o Raspberry Pi DENTRO de la red
del recinto, toma una foto de cada cámara cada N segundos y la sube a la API
por HTTPS. Solo hace conexiones de salida: no hay que abrir puertos.

    pip install requests          # y tener ffmpeg instalado
    python capturador.py camaras.json

Fuentes admitidas por cámara ("fuente"):
  * rtsp://...   stream de la cámara o del NVR (se toma 1 cuadro con ffmpeg)
  * http(s)://   URL de snapshot que devuelve un JPEG
  * ruta local   video o imagen (para probar sin cámaras)
Las credenciales de las cámaras viven SOLO en este archivo (permisos 600).
"""
from __future__ import annotations

import json
import logging
import os
import random
import signal
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote, urlsplit, urlunsplit

import requests

log = logging.getLogger("capturador")


@dataclass
class Camara:
    codigo: str
    api_key: str
    fuente: str
    intervalo_seg: int = 300
    usuario: str | None = None
    clave: str | None = None
    proxima: float = field(default=0.0)
    fallos: int = 0


def url_con_credenciales(url: str, usuario: str | None, clave: str | None) -> str:
    if not usuario:
        return url
    p = urlsplit(url)
    netloc = f"{quote(usuario, safe='')}:{quote(clave or '', safe='')}@{p.hostname}" + (f":{p.port}" if p.port else "")
    return urlunsplit((p.scheme, netloc, p.path, p.query, p.fragment))


def capturar(c: Camara, timeout: int = 20) -> bytes:
    if c.fuente.startswith("rtsp://"):
        cmd = ["ffmpeg", "-nostdin", "-loglevel", "error", "-rtsp_transport", "tcp",
               "-i", url_con_credenciales(c.fuente, c.usuario, c.clave),
               "-frames:v", "1", "-q:v", "3", "-f", "image2", "-vcodec", "mjpeg", "pipe:1"]
    elif c.fuente.startswith(("http://", "https://")):
        auth = requests.auth.HTTPDigestAuth(c.usuario, c.clave) if c.usuario else None
        r = requests.get(c.fuente, auth=auth, timeout=timeout)
        if r.status_code == 401 and c.usuario:          # algunas cámaras usan Basic
            r = requests.get(c.fuente, auth=(c.usuario, c.clave or ""), timeout=timeout)
        r.raise_for_status()
        return r.content
    else:
        ruta = Path(c.fuente)
        if ruta.suffix.lower() in (".jpg", ".jpeg", ".png"):
            return ruta.read_bytes()
        # video local: un cuadro al azar, como si fuera la cámara en otro momento
        duracion = 60.0
        try:
            salida = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(ruta)],
                                    capture_output=True, text=True, timeout=10)
            duracion = float(salida.stdout.strip() or 60)
        except (ValueError, subprocess.SubprocessError):
            pass
        cmd = ["ffmpeg", "-nostdin", "-loglevel", "error", "-ss", f"{random.uniform(0, max(0.1, duracion - 1)):.2f}",
               "-i", str(ruta), "-frames:v", "1", "-q:v", "3", "-f", "image2", "-vcodec", "mjpeg", "pipe:1"]
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=timeout)
    except FileNotFoundError:
        raise RuntimeError("ffmpeg no está instalado en el capturador (sudo apt install ffmpeg)")
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"La cámara no respondió en {timeout} s (revisa IP, puerto 554 y que el NVR esté encendido)")
    if r.returncode != 0 or not r.stdout:
        # nunca registrar la URL con credenciales
        raise RuntimeError(f"ffmpeg no obtuvo imagen: {r.stderr.decode(errors='ignore')[-300:].replace(c.clave or '§', '***')}")
    return r.stdout


class Capturador:
    def __init__(self, ruta_config: Path):
        cfg = json.loads(ruta_config.read_text(encoding="utf-8"))
        self.api = os.environ.get("STOCKEYE_API_URL") or cfg["api_url"]
        self.verificar = cfg.get("verificar_tls", True)
        self.camaras = [Camara(**{k: v for k, v in c.items() if k in Camara.__dataclass_fields__}) for c in cfg["camaras"]]
        self.http = requests.Session()
        self.detener = False
        if os.name == "posix" and ruta_config.stat().st_mode & 0o077:
            log.warning("%s tiene credenciales y es legible por otros usuarios: chmod 600 %s", ruta_config, ruta_config)
        # repartir las capturas para no golpear el NVR con todas a la vez
        for i, c in enumerate(self.camaras):
            c.proxima = time.monotonic() + i * min(10, c.intervalo_seg / max(1, len(self.camaras)))

    def subir(self, c: Camara, jpeg: bytes) -> None:
        r = self.http.post(self.api, headers={"X-API-Key": c.api_key},
                           data={"camara": c.codigo, "capturada_en": datetime.now(timezone.utc).isoformat()},
                           files={"foto": (f"{c.codigo}.jpg", jpeg, "image/jpeg")}, timeout=30, verify=self.verificar)
        if r.status_code == 401:
            raise PermissionError("API key rechazada: regenera la clave en el panel de administración")
        r.raise_for_status()

    def reportar_error(self, c: Camara, detalle: str) -> None:
        try:
            self.http.post(self.api.rstrip("/") + "/error", headers={"X-API-Key": c.api_key},
                           json={"detalle": detalle[:900]}, timeout=10, verify=self.verificar)
        except requests.RequestException:
            pass

    def ciclo(self, c: Camara) -> None:
        try:
            jpeg = capturar(c)
            self.subir(c, jpeg)
            c.fallos = 0
            log.info("%s: foto subida (%d KB)", c.codigo, len(jpeg) // 1024)
            c.proxima = time.monotonic() + c.intervalo_seg
        except Exception as e:
            c.fallos += 1
            # reintento con espera creciente (máx. el intervalo normal)
            c.proxima = time.monotonic() + min(c.intervalo_seg, 15 * 2 ** min(c.fallos, 5))
            log.error("%s: %s (fallo %d)", c.codigo, e, c.fallos)
            if not isinstance(e, requests.ConnectionError):
                self.reportar_error(c, str(e))

    def correr(self) -> None:
        signal.signal(signal.SIGTERM, lambda *_: setattr(self, "detener", True))
        signal.signal(signal.SIGINT, lambda *_: setattr(self, "detener", True))
        log.info("Capturador iniciado: %d cámaras → %s", len(self.camaras), self.api)
        while not self.detener:
            ahora = time.monotonic()
            for c in self.camaras:
                if c.proxima <= ahora and not self.detener:
                    self.ciclo(c)
            time.sleep(1)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    if len(sys.argv) != 2:
        raise SystemExit("Uso: python capturador.py camaras.json")
    Capturador(Path(sys.argv[1])).correr()
