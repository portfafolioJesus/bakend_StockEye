"""Firebase Cloud Messaging (API HTTP v1) sin SDK: JWT de la cuenta de servicio → token OAuth."""
from __future__ import annotations

import json
import time
from pathlib import Path

import httpx
import jwt

ALCANCE = "https://www.googleapis.com/auth/firebase.messaging"


class TokenInvalido(Exception):
    """El dispositivo ya no existe (app desinstalada o token rotado): se borra."""


class ClienteFCM:
    def __init__(self, ruta_credenciales: Path):
        cred = json.loads(Path(ruta_credenciales).read_text(encoding="utf-8"))
        self.proyecto = cred["project_id"]
        self._email, self._clave = cred["client_email"], cred["private_key"]
        self._uri_token = cred.get("token_uri", "https://oauth2.googleapis.com/token")
        self._token, self._vence = None, 0.0
        self._http = httpx.Client(timeout=15)

    def _acceso(self) -> str:
        if self._token and time.time() < self._vence - 60:
            return self._token
        ahora = int(time.time())
        asercion = jwt.encode({"iss": self._email, "scope": ALCANCE, "aud": self._uri_token,
                               "iat": ahora, "exp": ahora + 3600}, self._clave, algorithm="RS256")
        r = self._http.post(self._uri_token, data={"grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
                                                   "assertion": asercion})
        r.raise_for_status()
        datos = r.json()
        self._token, self._vence = datos["access_token"], time.time() + int(datos.get("expires_in", 3600))
        return self._token

    def enviar(self, token: str, titulo: str, cuerpo: str, datos: dict[str, str]) -> None:
        mensaje = {"message": {
            "token": token,
            "notification": {"title": titulo, "body": cuerpo},
            "data": {k: str(v) for k, v in datos.items() if v is not None},
            "android": {"priority": "high", "notification": {"channel_id": "tickets", "tag": datos.get("numero")}},
        }}
        r = self._http.post(f"https://fcm.googleapis.com/v1/projects/{self.proyecto}/messages:send",
                            headers={"Authorization": f"Bearer {self._acceso()}"}, json=mensaje)
        if r.status_code == 404 or (r.status_code == 400 and "INVALID_ARGUMENT" in r.text and "token" in r.text):
            raise TokenInvalido(r.text[:200])
        r.raise_for_status()
