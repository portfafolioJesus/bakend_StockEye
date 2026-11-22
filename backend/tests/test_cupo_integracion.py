"""Cola real y PostgreSQL aislado, con proveedor de visión simulado."""
from contextlib import contextmanager
from uuid import uuid4
import os

import psycopg
from psycopg.rows import dict_row

from conftest import jpg, procesar_todo
from stockeye.clasificacion.servicio import Clasificador
from stockeye.core.almacenamiento import almacenamiento
from stockeye.core.config import ajustes
from stockeye.ia.proveedor import ClasificacionIA, ErrorIA


class VisionFalsa:
    def __init__(self, error=None, callback=None):
        self.error = error
        self.callback = callback
        self.llamadas = 0

    def clasificar(self, imagen, categorias):
        self.llamadas += 1
        assert imagen and any(c["codigo"] == "LACTEOS" for c in categorias)
        if self.callback:
            self.callback()
        if self.error:
            raise self.error
        return ClasificacionIA(proveedor="groq",modelo="vision-prueba",
                               categoria_codigo="LACTEOS",decision="IDENTIFICADA",
                               producto="Yogures visibles",confianza=0.91,
                               descripcion="Envases de yogur visibles",tokens_entrada=100,tokens_salida=20)


@contextmanager
def clasificador(conn, *, error=None, callback=None, activo=True):
    conn.execute("UPDATE configuracion_ia SET activo=%s,proveedor='groq',modelo='vision-prueba'",[activo])
    falso = VisionFalsa(error=error,callback=callback)
    a = ajustes().model_copy(update={"clasificacion_intervalo_llamadas_s":0.0})
    servicio = Clasificador(a,fabrica_proveedor=lambda *_:falso)
    try:
        yield servicio,falso
    finally:
        servicio.conn.close()


def foto(conn, recinto=1):
    ruta = "pruebas/" + uuid4().hex + ".jpg"
    almacenamiento().guardar(ruta,jpg())
    fuente = conn.execute("SELECT fn_fuente_carga_recinto(%s) AS id",[recinto]).fetchone()["id"]
    imagen = conn.execute("""
        INSERT INTO imagen(recinto_id,camara_id,origen,ruta_archivo,capturada_en,caracterizacion_detalle)
        VALUES (%s,%s,'CAMARA',%s,now(),%s::jsonb) RETURNING id""",
        [recinto,fuente,ruta,'{"nombre_original":"original.jpg","archivo_archivado":"R01/por_clasificar/_procesadas/original.jpg"}']
    ).fetchone()["id"]
    tarea = conn.execute("SELECT fn_encolar_clasificacion(%s) AS id",[imagen]).fetchone()["id"]
    return imagen,tarea


def manual_desde_otra_conexion(conn, imagen, categoria="BEBES", producto="Decisión humana"):
    """Simula el guardado del Supervisor mientras la respuesta externa está en vuelo."""
    with psycopg.connect(os.environ["STOCKEYE_TEST_DATABASE_URL"],row_factory=dict_row) as otra:
        info = otra.execute("SELECT recinto_id FROM imagen WHERE id=%s",[imagen]).fetchone()
        otra.execute("SELECT pg_advisory_xact_lock(727006,%s)",[info["recinto_id"]])
        cat = otra.execute("SELECT id FROM categoria WHERE codigo=%s",[categoria]).fetchone()["id"]
        supervisor = otra.execute("""
            SELECT u.id FROM usuario u JOIN usuario_recinto ur ON ur.usuario_id=u.id
            WHERE u.rol='SUPERVISOR' AND ur.recinto_id=%s ORDER BY u.id LIMIT 1""",[info["recinto_id"]]
        ).fetchone()["id"]
        otra.execute("""
            UPDATE imagen SET estado_caracterizacion='MANUAL',categoria_id=%s,
                producto_caracterizado=%s,caracterizada_por=%s,caracterizada_en=now(),
                version_caracterizacion=version_caracterizacion+1
             WHERE id=%s""",[cat,producto,supervisor,imagen])
        otra.execute("""
            UPDATE tarea SET estado='HECHA',terminada_en=now()
             WHERE tipo='CLASIFICAR_IMAGEN' AND (payload->>'imagen_id')::bigint=%s
               AND estado IN ('PENDIENTE','PROCESANDO')""",[imagen])
        otra.execute("SELECT fn_aplicar_caracterizacion(%s)",[imagen])


def vencer_pausa(conn):
    conn.execute("UPDATE incidencia_ia SET reintentar_en=now()-interval '1 second' WHERE resuelta_en IS NULL")
    conn.execute("UPDATE tarea SET disponible_en=now()-interval '1 second' WHERE tipo='CLASIFICAR_IMAGEN' AND estado='PENDIENTE'")


def test_exito_completa_categoria_ticket_y_version_sin_inventar_faltante(conn,worker):
    imagen,tarea_id = foto(conn)
    assert procesar_todo(worker(pct=20)) == 1
    ticket = conn.execute("""
        SELECT t.id FROM ticket t JOIN ticket_imagen ti ON ti.ticket_id=t.id
         WHERE ti.imagen_id=%s""",[imagen]).fetchone()["id"]
    with clasificador(conn) as (servicio,falso):
        tarea = servicio.tomar()
        assert tarea["id"] == tarea_id and tarea["payload"]["version_caracterizacion"] == 1
        servicio.procesar_seguro(tarea)
    fila = conn.execute("""
        SELECT i.estado_caracterizacion,i.version_caracterizacion,i.producto_caracterizado,
               i.caracterizacion_detalle,c.codigo
          FROM imagen i LEFT JOIN categoria c ON c.id=i.categoria_id WHERE i.id=%s""",[imagen]).fetchone()
    assert falso.llamadas == 1
    assert fila["estado_caracterizacion"] == "AUTOMATICA" and fila["codigo"] == "LACTEOS"
    assert fila["version_caracterizacion"] == 2 and fila["producto_caracterizado"] == "Yogures visibles"
    assert fila["caracterizacion_detalle"]["nombre_original"] == "original.jpg"
    assert fila["caracterizacion_detalle"]["archivo_archivado"].endswith("original.jpg")
    assert conn.execute("SELECT estado FROM tarea WHERE id=%s",[tarea_id]).fetchone()["estado"] == "HECHA"
    salida = conn.execute("""
        SELECT t.producto_faltante,c.codigo FROM ticket t
        LEFT JOIN categoria c ON c.id=t.categoria_id WHERE t.id=%s""",[ticket]).fetchone()
    assert salida == {"producto_faltante":None,"codigo":"LACTEOS"}
    assert conn.execute("SELECT count(*) AS n FROM ticket_imagen WHERE imagen_id=%s",[imagen]).fetchone()["n"] == 1


def test_cuota_pausa_ambas_sucursales_y_no_duplica_avisos_ni_agota_intentos(conn):
    foto(conn,1)
    foto(conn,2)
    error = ErrorIA("Cuota confirmada",codigo=429,motivo="CUOTA",esperar_s=3600)
    with clasificador(conn,error=error) as (servicio,falso):
        servicio.procesar_seguro(servicio.tomar())
        assert servicio.tomar() is None and falso.llamadas == 1
        vencer_pausa(conn)
        servicio.procesar_seguro(servicio.tomar())
        assert falso.llamadas == 2
    assert conn.execute("SELECT count(*) AS n FROM incidencia_ia WHERE resuelta_en IS NULL").fetchone()["n"] == 1
    avisos = conn.execute("""
        SELECT n.incidente_ia_id,u.rol FROM notificacion n JOIN usuario u ON u.id=n.usuario_id
        WHERE n.tipo='IA_CUOTA'""").fetchall()
    assert len(avisos) == 2 and all(a["rol"] == "SUPERVISOR" for a in avisos)
    tareas = conn.execute("SELECT estado,intentos FROM tarea WHERE tipo='CLASIFICAR_IMAGEN'").fetchall()
    assert len(tareas) == 2 and all(t == {"estado":"PENDIENTE","intentos":0} for t in tareas)


def test_sucursal_que_llega_despues_recibe_aviso_sin_otra_llamada(conn):
    foto(conn,1)
    error = ErrorIA("Cuota confirmada",codigo=429,motivo="CUOTA",esperar_s=3600)
    with clasificador(conn,error=error) as (servicio,falso):
        servicio.procesar_seguro(servicio.tomar())
        assert conn.execute("SELECT count(*) AS n FROM notificacion WHERE tipo='IA_CUOTA'").fetchone()["n"] == 1
        segunda,tarea_id = foto(conn,2)
        assert servicio.tomar() is None and falso.llamadas == 1
    assert conn.execute("SELECT count(*) AS n FROM notificacion WHERE tipo='IA_CUOTA'").fetchone()["n"] == 2
    assert conn.execute("SELECT estado_caracterizacion FROM imagen WHERE id=%s",[segunda]).fetchone()["estado_caracterizacion"] == "PENDIENTE"
    assert conn.execute("SELECT intentos FROM tarea WHERE id=%s",[tarea_id]).fetchone()["intentos"] == 0


def test_respuesta_en_vuelo_no_sobrescribe_caracterizacion_manual(conn):
    imagen,tarea_id = foto(conn)
    with clasificador(conn,callback=lambda:manual_desde_otra_conexion(conn,imagen)) as (servicio,falso):
        servicio.procesar_seguro(servicio.tomar())
    fila = conn.execute("""
        SELECT i.estado_caracterizacion,i.producto_caracterizado,i.version_caracterizacion,
               i.caracterizada_por,c.codigo FROM imagen i
        JOIN categoria c ON c.id=i.categoria_id WHERE i.id=%s""",[imagen]).fetchone()
    assert falso.llamadas == 1 and fila["estado_caracterizacion"] == "MANUAL"
    assert fila["producto_caracterizado"] == "Decisión humana" and fila["codigo"] == "BEBES"
    assert fila["version_caracterizacion"] == 2 and fila["caracterizada_por"] is not None
    assert conn.execute("SELECT estado FROM tarea WHERE id=%s",[tarea_id]).fetchone()["estado"] == "HECHA"


def test_ia_apagada_avisa_y_permite_revision_sin_detener_vacio(conn,worker):
    imagen,tarea_id = foto(conn)
    with clasificador(conn,activo=False) as (servicio,falso):
        servicio.procesar_seguro(servicio.tomar())
    assert falso.llamadas == 0
    assert conn.execute("SELECT estado_caracterizacion FROM imagen WHERE id=%s",[imagen]).fetchone()["estado_caracterizacion"] == "REVISION"
    assert conn.execute("SELECT motivo FROM incidencia_ia WHERE resuelta_en IS NULL").fetchone()["motivo"] == "CONFIGURACION"
    assert conn.execute("SELECT count(*) AS n FROM notificacion WHERE tipo='IA_CUOTA'").fetchone()["n"] == 1
    assert conn.execute("SELECT estado FROM tarea WHERE id=%s",[tarea_id]).fetchone()["estado"] == "ERROR"
    assert procesar_todo(worker(pct=20)) == 1
    assert conn.execute("SELECT estado FROM imagen WHERE id=%s",[imagen]).fetchone()["estado"] == "PROCESADA"


def test_recuperacion_reanuda_pendiente_y_preserva_manual(conn):
    primera,_ = foto(conn,1)
    segunda,_ = foto(conn,2)
    error = ErrorIA("Cuota confirmada",codigo=429,motivo="CUOTA",esperar_s=3600)
    with clasificador(conn,error=error) as (servicio,falso):
        servicio.procesar_seguro(servicio.tomar())
        manual_desde_otra_conexion(conn,segunda)
        vencer_pausa(conn)
        falso.error = None
        tarea = servicio.tomar()
        assert tarea["payload"]["imagen_id"] == primera
        servicio.procesar_seguro(tarea)
        assert servicio.tomar() is None and falso.llamadas == 2
    assert conn.execute("SELECT resuelta_en FROM incidencia_ia").fetchone()["resuelta_en"] is not None
    filas = conn.execute("""
        SELECT id,estado_caracterizacion,producto_caracterizado FROM imagen WHERE id=ANY(%s)
        ORDER BY id""",[[primera,segunda]]).fetchall()
    assert filas[0]["estado_caracterizacion"] == "AUTOMATICA"
    assert filas[1]["estado_caracterizacion"] == "MANUAL" and filas[1]["producto_caracterizado"] == "Decisión humana"
