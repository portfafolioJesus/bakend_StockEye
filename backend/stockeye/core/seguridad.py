"""Claves (bcrypt), JWT, API keys de cámaras y URLs firmadas para las fotos."""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

import bcrypt
import jwt

from .config import ajustes

ALGORITMO = "HS256"


def hash_clave(clave: str) -> str:
    return bcrypt.hashpw(clave.encode("utf-8"), bcrypt.gensalt(12)).decode()


def verificar_clave(clave: str, hash_guardado: str) -> bool:
    try:
        return bcrypt.checkpw(clave.encode("utf-8"), hash_guardado.encode())
    except ValueError:
        return False


def clave_temporal() -> str:
    alfabeto = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789"
    return "".join(secrets.choice(alfabeto) for _ in range(12))


def crear_token(usuario_id: int, rol: str, tipo: str = "acceso") -> str:
    a = ajustes()
    ahora = datetime.now(timezone.utc)
    duracion = timedelta(minutes=a.jwt_minutos_acceso) if tipo == "acceso" else timedelta(days=a.jwt_dias_refresco)
    datos = {"sub": str(usuario_id), "rol": rol, "tipo": tipo, "iat": ahora, "exp": ahora + duracion,
             "jti": secrets.token_hex(8)}
    return jwt.encode(datos, a.jwt_secreto, algorithm=ALGORITMO)


def leer_token(token: str, tipo: str = "acceso") -> dict:
    datos = jwt.decode(token, ajustes().jwt_secreto, algorithms=[ALGORITMO])
    if datos.get("tipo") != tipo:
        raise jwt.InvalidTokenError("Tipo de token incorrecto")
    return datos


# ---- API keys de cámaras: se muestran una vez; en la BD solo queda el hash ----

def nueva_api_key(codigo_camara: str) -> str:
    return f"stk_{codigo_camara.lower().replace('-', '')}_{secrets.token_urlsafe(24)}"


def hash_api_key(api_key: str) -> str:
    return "sha256$" + hashlib.sha256(api_key.encode("utf-8")).hexdigest()


# ---- URLs firmadas: <img src> no puede mandar el header Authorization ----

def _firma(ruta: str, expira: int) -> str:
    mensaje = f"{ruta}|{expira}".encode()
    digest = hmac.new(ajustes().jwt_secreto.encode(), mensaje, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest[:18]).decode().rstrip("=")


def url_firmada(ruta: str | None) -> str | None:
    if not ruta:
        return None
    # Expira en bloques de 10 min para que el navegador pueda cachear la misma URL.
    bloque = 600
    expira = (int(time.time()) // bloque + 1) * bloque + ajustes().url_firma_minutos * 60
    return f"/api/v1/archivos/{quote(ruta)}?exp={expira}&firma={_firma(ruta, expira)}"


def verificar_firma(ruta: str, expira: int, firma: str) -> bool:
    return expira >= time.time() and hmac.compare_digest(_firma(ruta, expira), firma)
