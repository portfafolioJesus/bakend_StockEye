"""Registro de versiones de modelo en `modelo_ia` a partir del manifiesto
que genera herramientas/empaquetar_modelo.py (lo usan el CLI y el panel)."""
from __future__ import annotations

import json

SQL_REGISTRAR = """
INSERT INTO modelo_ia (nombre, version, ruta_pesos, sha256_pesos, umbral_confianza, clases, familia,
                       parametros, metricas, map50)
VALUES (%(nombre)s, %(version)s, %(ruta)s, %(sha256)s, %(umbral)s, %(clases)s, %(familia)s,
        %(parametros)s, %(metricas)s, %(map50)s)
ON CONFLICT (nombre, version) DO UPDATE
   SET ruta_pesos = EXCLUDED.ruta_pesos, sha256_pesos = EXCLUDED.sha256_pesos,
       umbral_confianza = EXCLUDED.umbral_confianza, clases = EXCLUDED.clases, familia = EXCLUDED.familia,
       parametros = EXCLUDED.parametros, metricas = EXCLUDED.metricas, map50 = EXCLUDED.map50
RETURNING id"""

SQL_ACTIVAR = """
WITH apagar AS (UPDATE modelo_ia SET activo = FALSE WHERE activo AND id <> %(id)s)
UPDATE modelo_ia SET activo = TRUE, activado_en = now(), activado_por = %(usuario)s WHERE id = %(id)s
RETURNING id, nombre, version"""


def validar_manifiesto(m: dict) -> None:
    faltan = [k for k in ("nombre", "version", "familia", "archivo", "clases", "umbral_confianza") if k not in m]
    if faltan:
        raise ValueError(f"Manifiesto incompleto, faltan: {', '.join(faltan)}")
    if m["familia"] not in ("SEGFORMER", "YOLO"):
        raise ValueError("familia debe ser SEGFORMER o YOLO")
    if not str(m["archivo"]).endswith(".onnx"):
        raise ValueError("El worker solo carga modelos .onnx (sin PyTorch, por el límite de 4 GB de RAM)")
    if not 0 < float(m["umbral_confianza"]) < 1:
        raise ValueError("umbral_confianza fuera de rango")


def parametros_sql(m: dict, ruta_relativa: str) -> dict:
    validar_manifiesto(m)
    metricas = m.get("metricas") or {}
    return dict(nombre=m["nombre"], version=m["version"], ruta=ruta_relativa, sha256=m.get("sha256"),
                umbral=m["umbral_confianza"], clases=json.dumps(m["clases"]), familia=m["familia"],
                parametros=json.dumps(m.get("parametros") or {}), metricas=json.dumps(metricas),
                map50=metricas.get("map50"))
