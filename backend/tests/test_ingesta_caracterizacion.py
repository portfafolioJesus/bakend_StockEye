"""Flujo completo con fotos sintéticas y proveedores falsos: ninguna petición externa."""
import os
import time
from pathlib import Path

from conftest import jpg, procesar_todo, token

API = "/api/v1"


def importador_prueba(carpeta, espera=0):
    from stockeye.core.config import ajustes
    from stockeye.importador.servicio import Importador
    return Importador(ajustes(), carpeta=carpeta, espera_estable_s=espera)


def dejar(carpeta, nombre, datos):
    carpeta.mkdir(parents=True, exist_ok=True)
    archivo = carpeta / nombre
    archivo.write_bytes(datos)
    anterior = time.time() - 10
    os.utime(archivo, (anterior, anterior))
    return archivo


def imagenes_importadas(conn):
    return conn.execute("""SELECT id,recinto_id,estado,estado_caracterizacion,version_caracterizacion,
                           caracterizacion_detalle FROM imagen WHERE importacion_clave IS NOT NULL ORDER BY id""").fetchall()


def test_lote_50_por_sucursal_ingresa_y_analiza_100_sin_agrupar(tmp_path, conn, worker):
    datos = jpg(80, 48)
    for recinto in ('R01', 'R02'):
        for n in range(50):
            dejar(tmp_path / recinto / 'por_clasificar', f'{n:03d}.jpg', datos)
    imp = importador_prueba(tmp_path)
    try:
        importadas = 0
        for _ in range(15):
            importadas += imp.revisar()
            if importadas == 100:
                break
        assert importadas == 100
        assert imp.revisar() == 0
    finally:
        imp.conn.close()
    fotos = imagenes_importadas(conn)
    assert len(fotos) == 100
    assert [f['recinto_id'] for f in fotos].count(1) == 50
    assert [f['recinto_id'] for f in fotos].count(2) == 50
    assert {f['estado_caracterizacion'] for f in fotos} == {'PENDIENTE'}
    tareas = conn.execute("""SELECT (payload->>'imagen_id')::bigint AS imagen_id FROM tarea
                            WHERE tipo='CLASIFICAR_IMAGEN'""").fetchall()
    assert len(tareas) == len({t['imagen_id'] for t in tareas}) == 100
    assert procesar_todo(worker(pct=20.0)) == 100
    ids = [f['id'] for f in fotos]
    resultado = conn.execute("""SELECT count(DISTINCT ti.ticket_id) AS tickets,count(*) AS fotos
                               FROM ticket_imagen ti WHERE ti.imagen_id=ANY(%s)""", [ids]).fetchone()
    assert resultado == {'tickets':100, 'fotos':100}
    assert {f['estado'] for f in imagenes_importadas(conn)} == {'PROCESADA'}
    # La clasificación no se ejecutó, pero tampoco frenó el cálculo local de vacío.
    assert conn.execute("SELECT count(*) AS n FROM tarea WHERE tipo='CLASIFICAR_IMAGEN' AND estado='PENDIENTE'").fetchone()['n'] == 100


def test_api_caracterizacion_permiso_sucursal_y_rol(tmp_path, conn, cliente):
    imp = importador_prueba(tmp_path)
    try:
        dejar(tmp_path / 'R01' / 'por_clasificar', 'uno.jpg', jpg(80,48))
        dejar(tmp_path / 'R02' / 'por_clasificar', 'dos.jpg', jpg(80,48))
        assert imp.revisar() == 2
    finally:
        imp.conn.close()
    fotos = imagenes_importadas(conn)
    r01 = next(f for f in fotos if f['recinto_id'] == 1)
    r02 = next(f for f in fotos if f['recinto_id'] == 2)
    sup = token(cliente, 'cmunoz@stockeye.test')
    rep = token(cliente, 'dsoto@stockeye.test')
    categoria = conn.execute("SELECT id FROM categoria WHERE codigo='BEBES'").fetchone()['id']
    datos = {'categoria_id':categoria,'producto':'Producto visible','version':0}
    assert cliente.get(f'{API}/caracterizaciones',params={'recinto_id':2},headers=sup).status_code == 403
    assert cliente.patch(f"{API}/caracterizaciones/{r02['id']}",json=datos,headers=sup).status_code == 403
    assert cliente.get(f'{API}/caracterizaciones',params={'recinto_id':1},headers=rep).status_code == 403
    assert cliente.patch(f"{API}/caracterizaciones/{r01['id']}",json=datos,headers=rep).status_code == 403
    assert {f['estado_caracterizacion'] for f in imagenes_importadas(conn)} == {'PENDIENTE'}


def test_manual_conserva_cero_y_distingue_sin_prediccion(tmp_path, conn, cliente, worker):
    imp = importador_prueba(tmp_path)
    try:
        dejar(tmp_path / 'R01' / 'por_clasificar', 'sin_vacio.jpg', jpg(80,48))
        assert imp.revisar() == 1
    finally:
        imp.conn.close()
    imagen = imagenes_importadas(conn)[0]['id']
    sup = token(cliente, 'cmunoz@stockeye.test')
    antes = cliente.get(f'{API}/caracterizaciones',params={'recinto_id':1},headers=sup).json()['imagenes'][0]
    assert antes['id'] == imagen and antes['porcentaje_vacio'] is None
    assert procesar_todo(worker(pct=0.0)) == 1
    despues = cliente.get(f'{API}/caracterizaciones',params={'recinto_id':1},headers=sup).json()['imagenes'][0]
    assert despues['porcentaje_vacio'] is not None and float(despues['porcentaje_vacio']) == 0.0
    categoria = conn.execute("SELECT id FROM categoria WHERE codigo='BEBES'").fetchone()['id']
    r = cliente.patch(f'{API}/caracterizaciones/{imagen}',json={'categoria_id':categoria,'version':0},headers=sup)
    assert r.status_code == 200, r.text
    assert r.json()['estado_caracterizacion'] == 'MANUAL'
    assert r.json()['producto_caracterizado'] is None
    assert float(r.json()['porcentaje_vacio']) == 0.0
    assert r.json()['ticket_numero'] is None
    assert conn.execute("SELECT estado FROM tarea WHERE tipo='CLASIFICAR_IMAGEN'").fetchone()['estado'] == 'HECHA'
    conflicto = cliente.patch(f'{API}/caracterizaciones/{imagen}',json={'categoria_id':categoria,'version':0},headers=sup)
    assert conflicto.status_code == 409


def test_archivar_manual_no_reingresa_imagen_ni_crea_ticket_extra(tmp_path, conn, cliente, worker):
    imp = importador_prueba(tmp_path)
    try:
        dejar(tmp_path / 'R01' / 'por_clasificar', 'archivo.jpg', jpg(80,48))
        assert imp.revisar() == 1
        imagen = imagenes_importadas(conn)[0]['id']
        assert procesar_todo(worker(pct=30)) == 1
        sup = token(cliente,'cmunoz@stockeye.test')
        categoria = conn.execute("SELECT id,nombre FROM categoria WHERE codigo='LACTEOS'").fetchone()
        r = cliente.patch(f'{API}/caracterizaciones/{imagen}',headers=sup,
                          json={'categoria_id':categoria['id'],'producto':'Productos lácteos visibles','version':0})
        assert r.status_code == 200, r.text
        assert imp.revisar() == 0
        foto = imagenes_importadas(conn)[0]
        archivo = tmp_path / foto['caracterizacion_detalle']['archivo_archivado']
        assert archivo.is_file()
        assert archivo.relative_to(tmp_path).parts[:3] == ('R01',categoria['nombre'],'_procesadas')
        assert imp.revisar() == 0
        assert len(imagenes_importadas(conn)) == 1
        assert conn.execute("SELECT count(*) AS n FROM ticket_imagen WHERE imagen_id=%s", [imagen]).fetchone()['n'] == 1
        assert conn.execute("SELECT count(*) AS n FROM tarea WHERE tipo='CLASIFICAR_IMAGEN'").fetchone()['n'] == 1
    finally:
        imp.conn.close()


def test_fallo_mover_despues_commit_reintenta_sin_duplicados(tmp_path, conn, monkeypatch):
    from stockeye.importador.servicio import PROCESADAS
    imp = importador_prueba(tmp_path)
    original = imp._mover
    llamadas = [0]
    def fallar_una_vez(archivo, subcarpeta, motivo=None):
        if subcarpeta == PROCESADAS and llamadas[0] == 0:
            llamadas[0] += 1
            raise OSError('Fallo de archivo simulado después del COMMIT')
        return original(archivo, subcarpeta, motivo)
    monkeypatch.setattr(imp,'_mover',fallar_una_vez)
    try:
        archivo = dejar(tmp_path / 'R01' / 'por_clasificar','reintento.jpg',jpg(80,48))
        assert imp.revisar() == 0
        assert archivo.is_file() and len(imagenes_importadas(conn)) == 1
        primero = imagenes_importadas(conn)[0]['id']
        assert imp.revisar() == 1
        assert not archivo.exists()
        assert [f['id'] for f in imagenes_importadas(conn)] == [primero]
        assert conn.execute("SELECT count(*) AS n FROM tarea WHERE tipo='CLASIFICAR_IMAGEN'").fetchone()['n'] == 1
    finally:
        imp.conn.close()


def test_archivo_que_crece_espera_estabilidad_entre_observaciones(tmp_path, monkeypatch):
    import stockeye.importador.servicio as modulo
    imp = importador_prueba(tmp_path,espera=0.01)
    reloj = [10.0]
    monkeypatch.setattr(modulo.time,'monotonic',lambda:reloj[0])
    monkeypatch.setattr(modulo.time,'time',lambda:1000.0)
    try:
        archivo = tmp_path / 'copia.jpg'
        archivo.write_bytes(b'primera parte')
        os.utime(archivo,(900,900))
        assert not imp._estable(archivo)
        reloj[0] += 0.02
        archivo.write_bytes(b'primera parte y segunda parte')
        os.utime(archivo,(900,900))
        assert not imp._estable(archivo)
        reloj[0] += 0.02
        assert imp._estable(archivo)
    finally:
        imp.conn.close()


def test_respuesta_automatica_en_vuelo_no_pisa_manual(tmp_path, conn, cliente):
    from stockeye.clasificacion.servicio import Clasificador
    from stockeye.core.config import ajustes
    from stockeye.ia.proveedor import ClasificacionIA
    imp = importador_prueba(tmp_path)
    try:
        dejar(tmp_path / 'R01' / 'por_clasificar','concurrente.jpg',jpg(80,48))
        assert imp.revisar() == 1
    finally:
        imp.conn.close()
    imagen = imagenes_importadas(conn)[0]['id']
    sup = token(cliente,'cmunoz@stockeye.test')
    categoria = conn.execute("SELECT id FROM categoria WHERE codigo='BEBES'").fetchone()['id']
    conn.execute("UPDATE configuracion_ia SET activo=TRUE,proveedor='falso',modelo='clasificacion-prueba'")
    version = [None]
    class ProveedorEnVuelo:
        def clasificar(self,foto,categorias):
            # La persona guarda mientras la llamada externa (falsa) está en curso.
            r = cliente.patch(f'{API}/caracterizaciones/{imagen}',headers=sup,
                              json={'categoria_id':categoria,'producto':'Decisión del Supervisor','version':version[0]})
            assert r.status_code == 200,r.text
            return ClasificacionIA('falso','clasificacion-prueba','LACTEOS',producto='Respuesta tardía',
                                   decision='IDENTIFICADA',confianza=0.99)
    a = ajustes().model_copy(update={'clasificacion_intervalo_llamadas_s':0})
    clasificador = Clasificador(a,fabrica_proveedor=lambda *args:ProveedorEnVuelo())
    try:
        tarea = clasificador.tomar()
        assert tarea is not None
        version[0] = tarea['payload']['version_caracterizacion']
        clasificador.procesar(tarea)
    finally:
        clasificador.conn.close()
    foto = conn.execute("SELECT estado_caracterizacion,categoria_id,producto_caracterizado,caracterizada_por FROM imagen WHERE id=%s", [imagen]).fetchone()
    assert foto == {'estado_caracterizacion':'MANUAL','categoria_id':categoria,
                    'producto_caracterizado':'Decisión del Supervisor','caracterizada_por':2}
    assert conn.execute("SELECT estado FROM tarea WHERE tipo='CLASIFICAR_IMAGEN'").fetchone()['estado'] == 'HECHA'
