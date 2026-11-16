"""Reglas de clasificación, incidentes y asignación: solo base aislada de pruebas."""
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4
import os

import psycopg
from psycopg.rows import dict_row


def captura(conn, recinto=1, pct=20, categoria=None):
    fuente = conn.execute("SELECT fn_fuente_carga_recinto(%s) AS id", [recinto]).fetchone()["id"]
    imagen = conn.execute("""INSERT INTO imagen (recinto_id, camara_id, origen, ruta_archivo, capturada_en, categoria_id)
                          VALUES (%s,%s,'CAMARA',%s,now(),%s) RETURNING id""",
                          [recinto, fuente, 'prueba/' + uuid4().hex + '.jpg', categoria]).fetchone()["id"]
    pred = conn.execute("""INSERT INTO prediccion (imagen_id,modelo_id,porcentaje_vacio,umbral_aplicado)
                        SELECT %s,id,%s,5 FROM modelo_ia WHERE activo RETURNING id""", [imagen,pct]).fetchone()["id"]
    return imagen, pred


def test_encolar_clasificacion_idempotente_y_preserva_manual(conn):
    imagen, _ = captura(conn)
    primero = conn.execute("SELECT fn_encolar_clasificacion(%s) AS id", [imagen]).fetchone()["id"]
    assert primero == conn.execute("SELECT fn_encolar_clasificacion(%s) AS id", [imagen]).fetchone()["id"]
    assert conn.execute("SELECT estado_caracterizacion FROM imagen WHERE id=%s", [imagen]).fetchone()["estado_caracterizacion"] == "PENDIENTE"
    conn.execute("UPDATE imagen SET estado_caracterizacion='MANUAL' WHERE id=%s", [imagen])
    assert conn.execute("SELECT fn_encolar_clasificacion(%s) AS id", [imagen]).fetchone()["id"] is None
    assert conn.execute("SELECT count(*) AS n FROM tarea WHERE tipo='CLASIFICAR_IMAGEN'").fetchone()["n"] == 1


def test_misma_categoria_no_mezcla_dos_ubicaciones_desconocidas(conn):
    categoria = conn.execute("SELECT id FROM categoria WHERE codigo='BEBES'").fetchone()["id"]
    fotos = [captura(conn, categoria=categoria) for _ in range(2)]
    tickets = [conn.execute("SELECT fn_ticket_desde_prediccion(%s) AS id", [pred]).fetchone()["id"] for _,pred in fotos]
    assert len(set(tickets)) == 2
    for (_, pred), ticket in zip(fotos, tickets):
        assert conn.execute("SELECT fn_ticket_desde_prediccion(%s) AS id", [pred]).fetchone()["id"] == ticket
    assert conn.execute("SELECT count(*) AS n FROM ticket_imagen WHERE imagen_id=ANY(%s)", [[i for i,_ in fotos]]).fetchone()["n"] == 2


def test_tickets_por_imagen_concurrentes_no_duplican_y_reparten_carga(conn):
    conn.execute("UPDATE ticket SET estado='CANCELADO' WHERE estado IN ('ABIERTO','ASIGNADO','EN_PROGRESO')")
    fotos = [captura(conn) for _ in range(9)]
    dsn = os.environ['STOCKEYE_TEST_DATABASE_URL']
    def crear(pred):
        with psycopg.connect(dsn, row_factory=dict_row) as c:
            return c.execute("SELECT fn_ticket_desde_prediccion(%s) AS id", [pred]).fetchone()["id"]
    with ThreadPoolExecutor(max_workers=4) as pool:
        resultado = list(pool.map(crear, [p for _,p in fotos] * 2))
    assert len(set(resultado)) == 9
    cargas = conn.execute("""SELECT asignado_a,count(*) AS n FROM ticket WHERE id=ANY(%s)
                             GROUP BY asignado_a ORDER BY asignado_a""", [list(set(resultado))]).fetchall()
    assert len(cargas) == 3 and {c['n'] for c in cargas} == {3}
    assert all(c['asignado_a'] is not None for c in cargas)


def test_asigna_menor_carga_y_no_al_supervisor_ni_otra_sucursal(conn):
    conn.execute("UPDATE ticket SET estado='CANCELADO' WHERE estado IN ('ABIERTO','ASIGNADO','EN_PROGRESO')")
    ids = [u['id'] for u in conn.execute("""SELECT u.id FROM usuario u JOIN usuario_recinto ur ON ur.usuario_id=u.id
                                          WHERE ur.recinto_id=1 AND u.rol='REPONEDOR' ORDER BY u.id""").fetchall()]
    for _ in range(2):
        conn.execute("""INSERT INTO ticket (titulo,origen,recinto_id,asignado_a)
                        VALUES ('Trabajo existente','MANUAL',1,%s)""", [ids[0]])
    _,pred = captura(conn)
    nuevo = conn.execute("SELECT fn_ticket_desde_prediccion(%s) AS id", [pred]).fetchone()["id"]
    asignado = conn.execute("SELECT asignado_a FROM ticket WHERE id=%s", [nuevo]).fetchone()['asignado_a']
    assert asignado in ids[1:]
    assert conn.execute("SELECT fn_autoasignar_ticket(%s) AS id", [nuevo]).fetchone()['id'] == asignado


def test_sin_reponedores_conserva_abierto_y_avisa_supervisor(conn):
    conn.execute("""UPDATE usuario SET activo=FALSE WHERE id IN
                    (SELECT u.id FROM usuario u JOIN usuario_recinto ur ON ur.usuario_id=u.id
                      WHERE ur.recinto_id=2 AND u.rol='REPONEDOR')""")
    _,pred = captura(conn, recinto=2)
    ticket = conn.execute("SELECT fn_ticket_desde_prediccion(%s) AS id", [pred]).fetchone()['id']
    fila = conn.execute("SELECT estado,asignado_a FROM ticket WHERE id=%s", [ticket]).fetchone()
    assert fila == {'estado':'ABIERTO','asignado_a':None}
    destinatarios = conn.execute("""SELECT u.rol,ur.recinto_id FROM notificacion n JOIN usuario u ON u.id=n.usuario_id
                                    JOIN usuario_recinto ur ON ur.usuario_id=u.id
                                   WHERE n.ticket_id=%s AND n.tipo='ALERTA_VACIO'""", [ticket]).fetchall()
    assert destinatarios and all(d == {'rol':'SUPERVISOR','recinto_id':2} for d in destinatarios)


def test_asignacion_automatica_registra_actor_sistema_y_restaura_usuario(conn):
    imagen,pred = captura(conn)
    with conn.transaction():
        conn.execute("SELECT set_config('app.usuario_id','6',true)")
        ticket = conn.execute("SELECT fn_ticket_desde_prediccion(%s) AS id", [pred]).fetchone()['id']
        assert conn.execute("SELECT app_usuario_actual() AS id").fetchone()['id'] == 6
    hist = conn.execute("""SELECT usuario_id,asignado_nuevo FROM historial_ticket
                            WHERE ticket_id=%s AND asignado_nuevo IS NOT NULL ORDER BY id DESC LIMIT 1""", [ticket]).fetchone()
    assert hist['usuario_id'] is None
    assert conn.execute("SELECT count(*) AS n FROM notificacion WHERE ticket_id=%s AND tipo='TICKET_ASIGNADO'", [ticket]).fetchone()['n'] == 1


def test_incidencia_solo_supervisores_afectados_sin_duplicar(conn):
    incidente = conn.execute("""INSERT INTO incidencia_ia(proveedor,modelo,motivo,mensaje)
                               VALUES ('falso','vision-test','CUOTA','Cuota agotada') RETURNING id""").fetchone()['id']
    conn.execute("INSERT INTO incidencia_ia_recinto VALUES (%s,1)", [incidente])
    assert conn.execute("SELECT fn_avisar_incidencia_ia(%s) AS n", [incidente]).fetchone()['n'] == 1
    assert conn.execute("SELECT fn_avisar_incidencia_ia(%s) AS n", [incidente]).fetchone()['n'] == 0
    conn.execute("INSERT INTO incidencia_ia_recinto VALUES (%s,2)", [incidente])
    assert conn.execute("SELECT fn_avisar_incidencia_ia(%s) AS n", [incidente]).fetchone()['n'] == 1
    destinatarios = conn.execute("""SELECT u.rol,n.ticket_id FROM notificacion n JOIN usuario u ON u.id=n.usuario_id
                                    WHERE n.incidente_ia_id=%s""", [incidente]).fetchall()
    assert len(destinatarios) == 2 and all(x == {'rol':'SUPERVISOR','ticket_id':None} for x in destinatarios)


def test_caracterizacion_completa_ticket_existente_sin_pisar_producto_manual(conn):
    imagen,pred = captura(conn)
    ticket = conn.execute("SELECT fn_ticket_desde_prediccion(%s) AS id", [pred]).fetchone()['id']
    conn.execute("UPDATE ticket SET producto_faltante='Descripción humana',enriquecido_ia=FALSE WHERE id=%s", [ticket])
    categoria = conn.execute("SELECT id FROM categoria WHERE codigo='LACTEOS'").fetchone()['id']
    conn.execute("""UPDATE imagen SET estado_caracterizacion='AUTOMATICA',categoria_id=%s,
                    producto_caracterizado='Sugerencia automática' WHERE id=%s""", [categoria,imagen])
    conn.execute("SELECT fn_aplicar_caracterizacion(%s)", [imagen])
    fila = conn.execute("SELECT categoria_id,producto_faltante FROM ticket WHERE id=%s", [ticket]).fetchone()
    assert fila == {'categoria_id':categoria,'producto_faltante':'Descripción humana'}
    conn.execute("""UPDATE imagen SET estado_caracterizacion='MANUAL',producto_caracterizado='Leche entera'
                    WHERE id=%s""", [imagen])
    conn.execute("SELECT fn_aplicar_caracterizacion(%s)", [imagen])
    assert conn.execute("SELECT producto_faltante,enriquecido_ia FROM ticket WHERE id=%s", [ticket]).fetchone() == {'producto_faltante':'Descripción humana','enriquecido_ia':False}
    assert conn.execute("SELECT producto_caracterizado FROM imagen WHERE id=%s", [imagen]).fetchone()['producto_caracterizado'] == 'Leche entera'
    assert conn.execute("SELECT count(*) AS n FROM ticket_imagen WHERE imagen_id=%s", [imagen]).fetchone()['n'] == 1


def test_foto_cierre_no_abre_incidente(conn):
    imagen,pred = captura(conn, pct=30)
    ticket = conn.execute("SELECT id FROM ticket WHERE numero='INC000004'").fetchone()['id']
    conn.execute("INSERT INTO ticket_imagen(ticket_id,imagen_id,tipo) VALUES (%s,%s,'CIERRE')", [ticket,imagen])
    assert conn.execute("SELECT fn_ticket_desde_prediccion(%s) AS id", [pred]).fetchone()['id'] is None
