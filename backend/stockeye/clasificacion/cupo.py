"""Pausa compartida por proveedor/modelo y un aviso por incidencia y destinatario."""
from __future__ import annotations

from ..ia.proveedor import ErrorIA


def identidad(a, config: dict) -> tuple[str, str]:
    proveedor = config.get("proveedor") or a.ia_proveedor
    modelo = a.ia_modelo or config.get("modelo") or {
        "groq": "qwen/qwen3.8-27b", "openai": "gpt-4.1-mini",
    }.get(proveedor, "predeterminado")
    return proveedor, modelo


def asociar_pendientes(conn, incidente_id: int, *, notificar: bool = True) -> None:
    conn.execute("""
        INSERT INTO incidencia_ia_recinto (incidencia_id, recinto_id)
        SELECT DISTINCT %s, recinto_id FROM tarea
         WHERE tipo IN ('CLASIFICAR_IMAGEN','ANALISIS_IA')
           AND estado IN ('PENDIENTE','PROCESANDO') AND recinto_id IS NOT NULL
        ON CONFLICT DO NOTHING""", [incidente_id])
    if notificar:
        conn.execute("SELECT fn_avisar_incidencia_ia(%s)", [incidente_id])


def pausa_activa(conn, a, config: dict) -> bool:
    proveedor, modelo = identidad(a, config)
    fila = conn.execute("""
        SELECT id, motivo FROM incidencia_ia
         WHERE proveedor=%s AND modelo=%s AND resuelta_en IS NULL
           AND reintentar_en > now()
        """, [proveedor, modelo]).fetchone()
    if fila:
        asociar_pendientes(conn, fila["id"], notificar=fila["motivo"] != "LIMITE_TEMPORAL")
    return bool(fila)


def registrar_pausa(conn, a, config: dict, error: ErrorIA, recinto_id: int | None = None) -> int:
    proveedor, modelo = identidad(a, config)
    motivo = error.motivo or "LIMITE_USO"
    espera = error.esperar_s or (
        getattr(a, "clasificacion_reintento_cuota_s", 3600) if motivo in ("CUOTA","CONFIGURACION") else 30)
    mensajes = {
        "CUOTA": "La IA de caracterización alcanzó su cuota de uso. El análisis de vacío continúa; puedes caracterizar las imágenes pendientes manualmente.",
        "CONFIGURACION": "La IA de caracterización no está disponible por su configuración. Puedes caracterizar las imágenes pendientes manualmente.",
        "LIMITE_TEMPORAL": "La caracterización automática está en pausa temporal y se reintentará. El análisis de vacío continúa.",
    }
    mensaje = mensajes.get(motivo,
        "La IA de caracterización alcanzó un límite de uso y está pausada. El análisis de vacío continúa; puedes caracterizar las imágenes pendientes manualmente.")
    fila = conn.execute("""
        INSERT INTO incidencia_ia (proveedor,modelo,motivo,mensaje,reintentar_en)
        VALUES (%s,%s,%s,%s,now()+make_interval(secs=>%s))
        ON CONFLICT (proveedor,modelo) WHERE resuelta_en IS NULL
        DO UPDATE SET motivo=EXCLUDED.motivo,mensaje=EXCLUDED.mensaje,
                      reintentar_en=GREATEST(incidencia_ia.reintentar_en,EXCLUDED.reintentar_en)
        RETURNING id,reintentar_en""", [proveedor,modelo,motivo,mensaje,float(espera)]).fetchone()
    if recinto_id is not None:
        conn.execute("""INSERT INTO incidencia_ia_recinto (incidencia_id,recinto_id)
                        VALUES (%s,%s) ON CONFLICT DO NOTHING""", [fila["id"],recinto_id])
    asociar_pendientes(conn, fila["id"], notificar=motivo != "LIMITE_TEMPORAL")
    # No gastar un intento de cada foto mientras se sabe que el proveedor está pausado.
    conn.execute("""
        UPDATE tarea SET disponible_en=GREATEST(disponible_en,%s)
         WHERE tipo IN ('CLASIFICAR_IMAGEN','ANALISIS_IA') AND estado='PENDIENTE'
    """, [fila["reintentar_en"]])
    return fila["id"]


def registrar_recuperacion(conn, a, config: dict) -> None:
    proveedor, modelo = identidad(a, config)
    conn.execute("""UPDATE incidencia_ia SET resuelta_en=now()
                    WHERE proveedor=%s AND modelo=%s AND resuelta_en IS NULL""", [proveedor,modelo])
