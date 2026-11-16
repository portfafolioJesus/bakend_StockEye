import json
from datos import CU
DATOS = {"G": "admin@stockeye.test / cmunoz@stockeye.test / dsoto@stockeye.test", "R": "dsoto@stockeye.test (reponedor R01)", "S": "cmunoz@stockeye.test (supervisora R01)", "A": "admin@stockeye.test", "M": "Cámara demo R01 + modelo activo"}
casos = []
n = 1
for c in CU:
    tipo = c["id"].split("-")[1][0]
    casos.append(dict(id=f"CP-{n:02d}", cu=c["id"], nombre=f"{c['nombre']} (flujo normal)", pre="; ".join(c["pre"]), pasos=c["flujo"], datos=DATOS[tipo], esperado=" ".join(c["post"])))
    n += 1
    for a in c["alt"]:
        cond, _, res = a.partition(": ")
        casos.append(dict(id=f"CP-{n:02d}", cu=c["id"], nombre=f"{c['nombre']} – {cond.split('. ',1)[-1]}", pre="; ".join(c["pre"]), pasos=[f"Seguir el flujo normal hasta el paso {cond.split('.')[0][:-1] or cond[:1]} con la condición: {cond.split('. ',1)[-1].lower()}."], datos=DATOS[tipo], esperado=res[:1].upper() + res[1:] if res else cond))
        n += 1
PYTEST = [
 ("test_carga.py", "test_carpeta_crea_estructura_e_importa", "La carpeta entradas/ crea la estructura e importa las fotos.", "CU-S05"),
 ("test_carga.py", "test_carpeta_con_codigo_de_gondola_sigue_funcionando", "Importar usando el código de góndola en la carpeta.", "CU-S05"),
 ("test_carga.py", "test_fuente_de_carga_no_aparece_como_camara", "El punto de carga virtual no se muestra como cámara real.", "CU-A04"),
 ("test_carga.py", "test_subir_fotos_desde_el_panel", "Carga de fotos desde el panel web.", "CU-S05"),
 ("test_carga.py", "test_un_ticket_activo_por_categoria_y_al_cerrar_abre_otro", "Un solo ticket activo por góndola/categoría; al cerrar se puede abrir otro.", "CU-M03"),
 ("test_cola.py", "test_rafaga_de_un_recinto_no_bloquea_a_otro", "Turnos por recinto en la cola de análisis.", "CU-M02"),
 ("test_cola.py", "test_worker_dedicado_solo_toma_su_recinto", "Worker dedicado a un recinto.", "CU-M02"),
 ("test_cola.py", "test_varios_workers_nunca_toman_la_misma_imagen", "Concurrencia: dos workers nunca toman la misma foto.", "CU-M02"),
 ("test_cola.py", "test_lease_recupera_imagen_de_worker_caido", "Si un worker cae, la foto vuelve a la cola.", "CU-M02"),
 ("test_cola.py", "test_archivo_faltante_va_a_error_sin_reintentos", "Una foto sin archivo pasa a ERROR.", "CU-M02"),
 ("test_cola.py", "test_ia_completa_producto_del_ticket_nuevo", "La IA completa el producto faltante del ticket.", "CU-M04"),
 ("test_cola.py", "test_ia_apagada_no_encola", "Con la IA desactivada no se encolan tareas.", "CU-A06"),
 ("test_cola.py", "test_notificador_sin_dispositivos_marca_enviadas", "El notificador no falla si el usuario no tiene dispositivos.", "CU-G03"),
 ("test_flujo.py", "test_camara_abre_ticket_y_luego_seguimiento", "Foto sobre el umbral abre ticket; la siguiente es seguimiento.", "CU-M03"),
 ("test_flujo.py", "test_bajo_umbral_no_abre_ticket", "Foto bajo el umbral no abre ticket.", "CU-M03"),
 ("test_flujo.py", "test_ingesta_rechaza_api_key_invalida", "La API rechaza una API key inválida.", "CU-M01"),
 ("test_flujo.py", "test_flujo_movil_resultado_ticket_y_cierre", "Flujo completo móvil: foto, ticket, cierre verificado.", "CU-R02, CU-R04"),
 ("test_flujo.py", "test_permisos_por_rol_y_recinto", "Cada rol solo ve y modifica lo de sus recintos.", "CU-G01"),
 ("test_flujo.py", "test_cancelar_exige_motivo", "Cancelar un ticket exige comentario.", "CU-S03"),
 ("test_flujo.py", "test_admin_crea_camara_y_la_clave_funciona", "La API key generada al crear una cámara funciona.", "CU-A04"),
 ("test_inferencia.py", "test_porcentaje_ignora_el_fondo", "El % de vacío no cuenta el fondo de la imagen.", "CU-M02"),
 ("test_inferencia.py", "test_sin_gondola", "Imagen sin góndola se maneja sin error.", "CU-M02"),
 ("test_inferencia.py", "test_anotada_es_jpeg", "La imagen anotada se genera en JPEG.", "CU-M02"),
 ("test_inferencia.py", "test_tope_de_pixeles_independiente_de_la_proporcion", "La resolución se limita por total de píxeles.", "CU-M02"),
 ("test_inferencia.py", "test_modelo_real_cumple_presupuesto_de_3_segundos", "El modelo real analiza una foto en menos de 3 s.", "CU-M02"),
]
REGLAS = [
 ("1", "Asignar a un reponedor de otro recinto", "Debe fallar", "ok: El usuario 7 no es un reponedor activo del recinto 1"),
 ("2", "Asignar un ticket a un supervisor", "Debe fallar", "ok: El usuario 2 no es un reponedor activo del recinto 1"),
 ("3", "Pasar a EN_PROGRESO sin responsable", "Debe fallar", "ok: viola ck_ticket_asignado"),
 ("4", "Segundo ticket de cámara abierto en la misma góndola", "Debe fallar", "ok: viola ux_ticket_camara_abierto_por_gondola"),
 ("5", "Imagen con góndola de otro recinto", "Debe fallar", "ok: viola la FK compuesta imagen_gondola_id_recinto_id_fkey"),
 ("6", "Imagen de CAMARA sin cámara", "Debe fallar", "ok: viola ck_imagen_origen"),
 ("7", "Dos modelos activos al mismo tiempo", "Debe fallar", "ok: viola ux_modelo_ia_un_activo"),
 ("8", "Asignación válida de un ticket ABIERTO", "Pasa a ASIGNADO con historial y notificación", "ok: asignado, con historial y notificación"),
]
json.dump(dict(casos=casos, pytest=PYTEST, reglas=REGLAS), open("pruebas.json", "w"), ensure_ascii=False, indent=1)
print(len(casos)); print(casos[1])
