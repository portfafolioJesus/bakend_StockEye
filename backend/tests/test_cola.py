"""Microservicios: equidad entre recintos, concurrencia, lease, IA y push."""
import threading

from conftest import jpg, procesar_todo

from stockeye.core.almacenamiento import almacenamiento


def encolar(conn, codigo_camara: str, n: int) -> list[int]:
    ids = []
    for i in range(n):
        ruta = f"recintos/prueba/{codigo_camara}_{i}.jpg"
        almacenamiento().guardar(ruta, jpg(64, 36))
        ids.append(conn.execute("""
            INSERT INTO imagen (recinto_id, gondola_id, camara_id, origen, ruta_archivo, capturada_en)
            SELECT recinto_id, gondola_id, id, 'CAMARA', %s, now() FROM camara WHERE codigo = %s
            RETURNING id""", [ruta, codigo_camara]).fetchone()["id"])
    return ids


def test_rafaga_de_un_recinto_no_bloquea_a_otro(conn, worker):
    encolar(conn, "R01-CAM04", 40)          # ráfaga en R01, encolada primero
    r02 = set(encolar(conn, "R02-CAM01", 3))
    w = worker(pct=1.0)
    orden = []
    while img := w.tomar():
        orden.append(img["id"])
        w.procesar_seguro(img)
    # Con turnos rotativos, las 3 de R02 salen entre las primeras 6 (y no al final de la fila de R01).
    assert r02 <= set(orden[:6]), orden[:8]
    assert len(orden) == 43


def test_worker_dedicado_solo_toma_su_recinto(conn, worker):
    encolar(conn, "R01-CAM04", 3)
    encolar(conn, "R02-CAM01", 2)
    w = worker(pct=1.0, nombre="r02", recintos="R02")
    assert procesar_todo(w) == 2
    assert conn.execute("SELECT count(*) n FROM imagen WHERE estado = 'PENDIENTE'").fetchone()["n"] == 3


def test_varios_workers_nunca_toman_la_misma_imagen(conn, worker):
    encolar(conn, "R01-CAM04", 30)
    encolar(conn, "R02-CAM01", 30)
    tomadas: list[int] = []
    candado = threading.Lock()

    def correr(w):
        while img := w.tomar():
            with candado:
                tomadas.append(img["id"])
            w.procesar_seguro(img)

    hilos = [threading.Thread(target=correr, args=(worker(pct=1.0, nombre=f"w{i}"),)) for i in range(3)]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join()
    assert len(tomadas) == 60 and len(set(tomadas)) == 60
    assert conn.execute("SELECT count(DISTINCT tomada_por) n FROM imagen WHERE tomada_por LIKE 'w%%'").fetchone()["n"] >= 2


def test_lease_recupera_imagen_de_worker_caido(conn):
    [img] = encolar(conn, "R01-CAM04", 1)
    conn.execute("""UPDATE imagen SET estado = 'PROCESANDO', tomada_por = 'muerto', intentos = 1,
                    tomada_en = now() - interval '10 minutes' WHERE id = %s""", [img])
    assert conn.execute("SELECT fn_recuperar_imagenes(5) n").fetchone()["n"] == 1
    assert conn.execute("SELECT estado FROM imagen WHERE id = %s", [img]).fetchone()["estado"] == "PENDIENTE"


def test_archivo_faltante_va_a_error_sin_reintentos(conn, worker):
    conn.execute("""INSERT INTO imagen (recinto_id, camara_id, gondola_id, origen, ruta_archivo, capturada_en)
                    SELECT recinto_id, id, gondola_id, 'CAMARA', 'recintos/R01/no-existe.jpg', now()
                      FROM camara WHERE codigo = 'R01-CAM04'""")
    procesar_todo(worker())
    fila = conn.execute("SELECT estado, error_detalle FROM imagen WHERE ruta_archivo LIKE '%%no-existe%%'").fetchone()
    assert fila["estado"] == "ERROR" and "No se encontró" in fila["error_detalle"]


class ProveedorFalso:
    nombre, modelo = "falso", "vision-test"

    def analizar(self, imagen_jpg, contexto):
        from stockeye.ia.proveedor import RespuestaIA
        return RespuestaIA("falso", "vision-test", [{"producto": "Cloro gel 900 ml", "categoria": "Limpieza",
                                                     "confianza": 0.81}], "Falta cloro", 100, 20, 50)

    def probar(self):
        return {"ok": True}


def test_ia_completa_producto_del_ticket_nuevo(conn, worker):
    from stockeye.core.config import ajustes
    from stockeye.ia import proveedor as prov
    from stockeye.ia.servicio import EnriquecedorIA
    prov.PROVEEDORES["falso"] = lambda a, m: ProveedorFalso()
    conn.execute("UPDATE configuracion_ia SET activo = TRUE, proveedor = 'falso'")
    encolar(conn, "R01-CAM04", 1)
    procesar_todo(worker(pct=15.0))                   # abre ticket y encola el análisis
    tarea = conn.execute("SELECT * FROM tarea").fetchone()
    assert tarea and tarea["payload"]["ticket_id"]
    ia = EnriquecedorIA(ajustes())
    try:
        t = ia.tomar()
        ia.procesar(t)
    finally:
        ia.conn.close(); ia.escucha.close()
    ticket = conn.execute("SELECT producto_faltante, enriquecido_ia FROM ticket WHERE id = %s",
                          [tarea["payload"]["ticket_id"]]).fetchone()
    assert ticket == {"producto_faltante": "Cloro gel 900 ml", "enriquecido_ia": True}


def test_ia_apagada_no_encola(conn, worker):
    encolar(conn, "R01-CAM04", 1)
    procesar_todo(worker(pct=15.0))
    assert conn.execute("SELECT count(*) n FROM tarea").fetchone()["n"] == 0


def test_notificador_sin_dispositivos_marca_enviadas(conn):
    from stockeye.core.config import ajustes
    from stockeye.notificador.servicio import Notificador
    n = Notificador(ajustes())
    try:
        while n.procesar_lote():
            pass
    finally:
        n.conn.close(); n.escucha.close()
    fila = conn.execute("SELECT count(*) FILTER (WHERE NOT enviada_push) pendientes, "
                        "count(*) FILTER (WHERE push_error = 'sin dispositivos') sin FROM notificacion").fetchone()
    assert fila["pendientes"] == 0 and fila["sin"] > 0
