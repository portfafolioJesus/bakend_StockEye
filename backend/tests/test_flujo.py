"""Escenario de PLAN.md (Fase 1): foto de cámara → INC; segunda foto → SEGUIMIENTO;
foto móvil → resultado → ticket; cierre verificado y reglas de permisos."""
from conftest import jpg, procesar_todo, token

API = "/api/v1"
CAM04 = {"X-API-Key": "demo-R01-CAM04"}       # P05-G03 · Limpieza (sin ticket abierto en el seed)


def subir_camara(cliente, headers=CAM04):
    r = cliente.post(f"{API}/ingesta", headers=headers, files={"foto": ("f.jpg", jpg(), "image/jpeg")})
    assert r.status_code == 202, r.text
    return r.json()["imagen_id"]


def test_camara_abre_ticket_y_luego_seguimiento(cliente, worker):
    sup = token(cliente, "cmunoz@stockeye.test")
    w = worker(pct=12.0)
    subir_camara(cliente)
    assert procesar_todo(w) == 1
    t = next(t for t in cliente.get(f"{API}/tickets", params={"recinto_id": 1}, headers=sup).json()["tickets"]
             if t["gondola_codigo"] == "P05-G03")
    assert (t["estado"], t["prioridad"], t["origen"], float(t["porcentaje_vacio"])) == ("ABIERTO", "MEDIA", "CAMARA", 12.0)

    w.motor_falso.pct = 25.0                         # empeora → seguimiento y la prioridad sube
    subir_camara(cliente)
    procesar_todo(w)
    d = cliente.get(f"{API}/tickets/{t['numero']}", headers=sup).json()
    assert [e["tipo"] for e in d["evidencias"]] == ["APERTURA", "SEGUIMIENTO"]
    assert d["ticket"]["prioridad"] == "ALTA" and float(d["ticket"]["porcentaje_vacio"]) == 25.0
    assert any("Nueva foto de la cámara: 25,0 %" in e["texto"] for e in d["linea_tiempo"])
    # la supervisora recibió la alerta
    tipos = [n["tipo"] for n in cliente.get(f"{API}/notificaciones", headers=sup).json()["notificaciones"]]
    assert "ALERTA_VACIO" in tipos


def test_bajo_umbral_no_abre_ticket(cliente, worker, conn):
    antes = conn.execute("SELECT count(*) n FROM ticket").fetchone()["n"]
    w = worker(pct=3.0)
    subir_camara(cliente)
    procesar_todo(w)
    assert conn.execute("SELECT count(*) n FROM ticket").fetchone()["n"] == antes
    assert conn.execute("SELECT estado FROM imagen ORDER BY id DESC LIMIT 1").fetchone()["estado"] == "PROCESADA"


def test_ingesta_rechaza_api_key_invalida(cliente):
    r = cliente.post(f"{API}/ingesta", headers={"X-API-Key": "otra"}, files={"foto": ("f.jpg", jpg(), "image/jpeg")})
    assert r.status_code == 401
    r = cliente.post(f"{API}/ingesta", headers=CAM04, files={"foto": ("f.jpg", b"no es imagen", "image/jpeg")})
    assert r.status_code == 422


def test_flujo_movil_resultado_ticket_y_cierre(cliente, worker):
    rep = token(cliente, "dsoto@stockeye.test")
    w = worker(pct=14.2)
    gondola = next(g for g in cliente.get(f"{API}/recintos/1/gondolas", headers=rep).json() if g["codigo"] == "P05-G03")
    img = cliente.post(f"{API}/imagenes", headers=rep, data={"gondola_id": gondola["id"]},
                       files={"foto": ("m.jpg", jpg(), "image/jpeg")}).json()["imagen_id"]
    assert cliente.post(f"{API}/tickets", headers=rep, json={"imagen_id": img}).status_code == 409   # aún en análisis
    procesar_todo(w)
    res = cliente.get(f"{API}/imagenes/{img}", headers=rep).json()
    assert res["prediccion"]["supera_umbral"] and res["ticket"] is None      # el worker NO crea el ticket móvil
    r = cliente.post(f"{API}/tickets", headers=rep, json={"imagen_id": img, "titulo": "Vacío detectado en P05-G03 · Limpieza",
                                                         "producto_faltante": "Cloro gel 900 ml", "comentario": "2 cajas en bodega"})
    assert r.status_code == 201, r.text
    t = r.json()["ticket"]
    # Todo ticket nuevo llega SIN ASIGNAR al supervisor, aunque lo cree un reponedor
    assert (t["origen"], t["estado"], t["asignado_nombre"]) == ("MOVIL", "ABIERTO", None)
    num = t["numero"]
    mios = cliente.get(f"{API}/tickets", headers=rep).json()["tickets"]
    assert num in [x["numero"] for x in mios]                      # el reponedor ve lo que reportó
    sup = token(cliente, "cmunoz@stockeye.test")
    assert num in [x["numero"] for x in cliente.get(f"{API}/tickets", params={"recinto_id": 1, "vista": "sin_asignar"},
                                                     headers=sup).json()["tickets"]]
    assert cliente.patch(f"{API}/tickets/{num}", headers=rep, json={"estado": "EN_PROGRESO"}).status_code in (403, 409)
    asignado = cliente.patch(f"{API}/tickets/{num}", headers=sup, json={"asignado_a": 4})
    assert asignado.json()["ticket"]["estado"] == "ASIGNADO"
    assert cliente.patch(f"{API}/tickets/{num}", headers=rep, json={"estado": "EN_PROGRESO"}).status_code == 200

    # foto de cierre sobre el umbral → cerrar exige comentario
    cierre = cliente.post(f"{API}/tickets/{num}/cierre", headers=rep, files={"foto": ("c.jpg", jpg(), "image/jpeg")})
    assert cliente.post(f"{API}/tickets/{num}/cerrar", headers=rep, json={}).status_code == 409    # analizando
    procesar_todo(w)
    assert cliente.post(f"{API}/tickets/{num}/cerrar", headers=rep, json={}).status_code == 422
    # repetir foto, ahora bajo el umbral → cierre verificado
    w.motor_falso.pct = 1.6
    cliente.post(f"{API}/tickets/{num}/cierre", headers=rep, files={"foto": ("c2.jpg", jpg(), "image/jpeg")})
    procesar_todo(w)
    r = cliente.post(f"{API}/tickets/{num}/cerrar", headers=rep, json={"comentario": "Repuesto con 2 cajas"})
    assert r.status_code == 200, r.text
    assert r.json()["ticket"]["estado"] == "CERRADO" and r.json()["ticket"]["cierre_verificado"]
    assert float(r.json()["ticket"]["pct_cierre"]) == 1.6
    assert cierre.status_code == 202


def test_permisos_por_rol_y_recinto(cliente):
    sup1 = token(cliente, "cmunoz@stockeye.test")
    rep = token(cliente, "dsoto@stockeye.test")
    assert cliente.get(f"{API}/tickets", params={"recinto_id": 2}, headers=sup1).status_code == 403
    assert cliente.get(f"{API}/tickets/INC000005", headers=sup1).status_code == 403          # ticket de R02
    # el reponedor solo ve lo suyo y no puede reasignar
    mios = cliente.get(f"{API}/tickets", headers=rep).json()["tickets"]
    assert mios and all(t["asignado_nombre"] == "Diego Soto" for t in mios)
    assert cliente.patch(f"{API}/tickets/INC000001", headers=rep, json={"asignado_a": 5}).status_code == 403
    # regla de la BD: no se asigna a un reponedor de otro recinto
    r = cliente.patch(f"{API}/tickets/INC000003", headers=sup1, json={"asignado_a": 7})
    assert r.status_code == 409 and "no es un reponedor activo" in r.json()["detail"]
    r = cliente.patch(f"{API}/tickets/INC000003", headers=sup1, json={"asignado_a": 4})
    assert r.json()["ticket"]["estado"] == "ASIGNADO"
    assert cliente.get(f"{API}/admin/usuarios", headers=sup1).status_code == 403
    assert cliente.get(f"{API}/tickets").status_code == 401


def test_cancelar_exige_motivo(cliente):
    sup = token(cliente, "cmunoz@stockeye.test")
    assert cliente.patch(f"{API}/tickets/INC000003", headers=sup, json={"estado": "CANCELADO"}).status_code == 422
    r = cliente.patch(f"{API}/tickets/INC000003", headers=sup, json={"estado": "CANCELADO", "comentario": "Producto descontinuado"})
    assert r.json()["ticket"]["estado"] == "CANCELADO"


def test_admin_crea_camara_y_la_clave_funciona(cliente):
    adm = token(cliente, "admin@stockeye.test")
    r = cliente.post(f"{API}/admin/camaras", headers=adm, json={"recinto_id": 1, "codigo": "R01-CAM09", "intervalo_captura_seg": 60})
    assert r.status_code == 201
    clave = r.json()["api_key"]
    assert subir_camara(cliente, {"X-API-Key": clave}) > 0
    malo = cliente.post(f"{API}/admin/camaras", headers=adm,
                        json={"recinto_id": 1, "codigo": "R01-CAM10", "url_stream": "rtsp://user:clave@10.0.0.2/1"})
    assert malo.status_code == 422                                     # nunca credenciales en la BD
    u = cliente.post(f"{API}/admin/usuarios", headers=adm, json={"nombre": "Ana", "apellido": "Paz", "email": "ana@stockeye.test",
                                                                 "rol": "REPONEDOR", "recintos": [1]}).json()
    r = cliente.post(f"{API}/auth/login", json={"email": "ana@stockeye.test", "clave": u["clave_temporal"]})
    assert r.status_code == 200 and r.json()["usuario"]["debe_cambiar_clave"]
