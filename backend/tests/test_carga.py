"""Fotos reales por carpeta (importador) y desde el panel (POST /imagenes/carga)."""
import os
import time

from conftest import jpg, procesar_todo, token

API = "/api/v1"


def importador(tmp_path):
    from stockeye.core.config import ajustes
    from stockeye.importador.servicio import Importador
    return Importador(ajustes(), carpeta=tmp_path, espera_estable_s=0)


def dejar(carpeta, nombre, datos, antiguedad_s=5):
    carpeta.mkdir(parents=True, exist_ok=True)
    archivo = carpeta / nombre
    archivo.write_bytes(datos)
    t = time.time() - antiguedad_s
    os.utime(archivo, (t, t))
    return archivo


def test_carpeta_crea_estructura_e_importa(tmp_path, conn, worker):
    imp = importador(tmp_path)
    try:
        imp.revisar()                                       # crea entradas/R01/<categoría>/ … y el LEEME
        assert (tmp_path / "LEEME.txt").is_file()
        assert (tmp_path / "R01" / "Limpieza").is_dir() and (tmp_path / "R02" / "Bebidas y jugos").is_dir()
        destino = tmp_path / "R01" / "Limpieza"
        dejar(destino, "gondola.jpg", jpg())
        dejar(destino, "notas.txt", b"no es foto")             # se ignora
        dejar(destino, "malo.jpg", b"esto no es un jpeg")      # se rechaza con motivo
        assert imp.revisar() == 1
    finally:
        imp.conn.close()
    assert not (destino / "gondola.jpg").exists() and list((destino / "_procesadas").rglob("gondola.jpg"))
    rechazada = list((destino / "_rechazadas").rglob("malo.jpg"))
    assert rechazada and "no es una imagen" in rechazada[0].with_suffix(".jpg.txt").read_text()
    assert (destino / "notas.txt").exists()
    fila = conn.execute("""SELECT i.estado, i.origen, c.tipo, c.codigo, i.ruta_archivo, cat.codigo cat
                             FROM imagen i JOIN camara c ON c.id = i.camara_id JOIN categoria cat ON cat.id = i.categoria_id
                            ORDER BY i.id DESC LIMIT 1""").fetchone()
    assert (fila["estado"], fila["origen"], fila["tipo"], fila["cat"]) == ("PENDIENTE", "CAMARA", "CARGA", "LIMPIEZA")
    assert fila["codigo"] == "R01-CARGA" and fila["ruta_archivo"].startswith("recintos/R01/")

    # Punto fijo: una subcarpeta dentro de la categoría → como una cámara (2ª foto = SEGUIMIENTO)
    w = worker(pct=18.0)
    procesar_todo(w)
    punto = destino / "Pasillo central"
    for nombre in ("p1.jpg", "p2.jpg"):
        imp = importador(tmp_path)
        try:
            dejar(punto, nombre, jpg())
            imp.revisar()
        finally:
            imp.conn.close()
        procesar_todo(w)
    t = conn.execute("""SELECT array_agg(ti.tipo::text ORDER BY ti.agregada_en) tipos, t.estado
                          FROM ticket t JOIN ticket_imagen ti ON ti.ticket_id = t.id
                          JOIN gondola g ON g.id = t.gondola_id WHERE g.descripcion = 'Pasillo central' GROUP BY t.id""").fetchone()
    assert t["tipos"] == ["APERTURA", "SEGUIMIENTO"] and t["estado"] == "ABIERTO"       # sin asignar


def test_carpeta_con_codigo_de_gondola_sigue_funcionando(tmp_path, conn):
    imp = importador(tmp_path)
    try:
        dejar(tmp_path / "R01" / "P05-G03", "f.jpg", jpg())
        imp.revisar()
    finally:
        imp.conn.close()
    fila = conn.execute("SELECT g.codigo FROM imagen i JOIN gondola g ON g.id = i.gondola_id ORDER BY i.id DESC LIMIT 1").fetchone()
    assert fila["codigo"] == "P05-G03"


def test_fuente_de_carga_no_aparece_como_camara(tmp_path, cliente, conn):
    imp = importador(tmp_path)
    try:
        dejar(tmp_path / "R01" / "Limpieza", "f.jpg", jpg())
        imp.revisar()
    finally:
        imp.conn.close()
    adm = token(cliente, "admin@stockeye.test")
    codigos = [c["codigo"] for c in cliente.get(f"{API}/admin/camaras", headers=adm).json()]
    assert not any("CARGA" in c for c in codigos)
    r01 = next(r for r in cliente.get(f"{API}/admin/recintos", headers=adm).json() if r["codigo"] == "R01")
    assert r01["camaras"] == 5                               # las 5 cámaras IP del seed


def test_subir_fotos_desde_el_panel(cliente, conn, worker):
    sup = token(cliente, "cmunoz@stockeye.test")
    g = next(x for x in cliente.get(f"{API}/recintos/1/gondolas", headers=sup).json() if x["codigo"] == "P05-G03")
    r = cliente.post(f"{API}/imagenes/carga", headers=sup, data={"gondola_id": g["id"]},
                     files=[("fotos", ("a.jpg", jpg(), "image/jpeg")), ("fotos", ("b.txt", b"hola", "text/plain"))])
    assert r.status_code == 202, r.text
    res = r.json()["resultados"]
    assert "imagen_id" in res[0] and "error" in res[1]
    procesar_todo(worker(pct=30.0))
    img = cliente.get(f"{API}/imagenes/{res[0]['imagen_id']}", headers=sup).json()
    assert img["estado"] == "PROCESADA" and img["ticket"]["tipo"] == "APERTURA"
    d = cliente.get(f"{API}/tickets/{img['ticket']['numero']}", headers=sup).json()
    assert d["ticket"]["camara_tipo"] == "CARGA"
    assert any("foto cargada" in e["texto"] for e in d["linea_tiempo"])
    # el reponedor no puede usar la carga del panel; un supervisor de otro recinto tampoco
    rep = token(cliente, "dsoto@stockeye.test")
    assert cliente.post(f"{API}/imagenes/carga", headers=rep, data={"gondola_id": g["id"]},
                        files=[("fotos", ("a.jpg", jpg(), "image/jpeg"))]).status_code == 403
    sup2 = token(cliente, "pcontreras@stockeye.test")
    assert cliente.post(f"{API}/imagenes/carga", headers=sup2, data={"gondola_id": g["id"]},
                        files=[("fotos", ("a.jpg", jpg(), "image/jpeg"))]).status_code == 403


def test_un_ticket_activo_por_categoria_y_al_cerrar_abre_otro(tmp_path, conn, worker, cliente):
    """Fotos solo con categoría: la 2ª se suma como SEGUIMIENTO; tras cerrar, la siguiente abre un ticket nuevo."""
    w = worker(pct=15.0)
    def cargar(nombre):
        imp = importador(tmp_path)
        try:
            dejar(tmp_path / "R01" / "Lácteos y huevos", nombre, jpg())
            imp.revisar()
        finally:
            imp.conn.close()
        procesar_todo(w)
    cargar("a.jpg"); cargar("b.jpg")
    tickets = conn.execute("""SELECT t.numero, t.estado, t.categoria_id, array_agg(ti.tipo::text ORDER BY ti.agregada_en) tipos
                                FROM ticket t JOIN ticket_imagen ti ON ti.ticket_id = t.id
                               WHERE t.categoria_id = (SELECT id FROM categoria WHERE codigo = 'LACTEOS') AND t.gondola_id IS NULL
                               GROUP BY t.id""").fetchall()
    assert len(tickets) == 1 and tickets[0]["tipos"] == ["APERTURA", "SEGUIMIENTO"] and tickets[0]["estado"] == "ABIERTO"
    conn.execute("UPDATE ticket SET estado='CANCELADO' WHERE numero = %s", [tickets[0]["numero"]])
    cargar("c.jpg")
    n = conn.execute("""SELECT count(*) n FROM ticket WHERE gondola_id IS NULL AND origen='CAMARA'
                         AND categoria_id = (SELECT id FROM categoria WHERE codigo='LACTEOS')""").fetchone()["n"]
    assert n == 2
