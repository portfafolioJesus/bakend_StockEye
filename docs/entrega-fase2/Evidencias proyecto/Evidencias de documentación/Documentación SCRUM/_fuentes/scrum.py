# Backlog SCRUM de StockEye: épicas, sprints e historias de usuario.
import json

EPICAS = [
    ("EP-01", "Datos y modelo de visión", "Construir el dataset y entrenar, evaluar y empaquetar el modelo que calcula el % de vacío.", "SKT-3 a SKT-7 (CRISP-DM)", "Ignacio Ruz"),
    ("EP-02", "Acceso y usuarios", "Ingreso seguro con roles y recintos.", "SKT-8 Codificación", "Jesús González / Claudio Galiano"),
    ("EP-03", "Captura y análisis de imágenes", "Recibir fotos de cámaras, celulares y panel, y analizarlas en cola.", "SKT-8 Codificación", "Jesús González / Ignacio Ruz"),
    ("EP-04", "Gestión de tickets de reposición", "Abrir, asignar, atender y cerrar tickets con evidencia.", "SKT-8 Codificación", "Jesús González / Claudio Galiano"),
    ("EP-05", "Notificaciones e IA de producto", "Avisar en tiempo real y sugerir el producto faltante.", "SKT-8 Codificación", "Jesús González"),
    ("EP-06", "Supervisión y reportes", "Bandeja, carga del equipo e indicadores para el supervisor.", "SKT-8 Codificación", "Jesús González / Claudio Galiano"),
    ("EP-07", "Administración del sistema", "Recintos, góndolas, cámaras, usuarios y versiones del modelo.", "SKT-8 Codificación", "Jesús González / Ignacio Ruz"),
    ("EP-08", "Calidad, despliegue y documentación", "Pruebas, instalación reproducible y documentación final.", "SKT-9 Despliegue y cierre", "Todo el equipo"),
]

SPRINTS = [
    ("Sprint 0", "Agosto, semanas 1–2", "Arrancar el proyecto: kickoff con Walmart, organización del equipo, tablero y Carta Gantt.", ["HU-00"]),
    ("Sprint 1", "Agosto, semanas 3–4", "Entender el problema: requisitos, casos de uso, tecnologías y entorno de entrenamiento.", ["HU-01", "HU-02"]),
    ("Sprint 2", "Septiembre, semanas 1–2", "Comprender y preparar los datos: imágenes reales, datasets públicos, etiquetado.", ["HU-03"]),
    ("Sprint 3", "Septiembre, semanas 3–4", "Primer modelo: YOLO baseline, métricas, cálculo de % de vacío.", ["HU-04", "HU-05"]),
    ("Sprint 4", "Octubre, semanas 1–2", "Cambio a segmentación (SegFormer → ONNX), diseño de la base de datos y prototipos de interfaz.", ["HU-06", "HU-07", "HU-24"]),
    ("Sprint 5", "Octubre, semanas 3–4", "Núcleo del sistema: login, recepción de fotos, cola de análisis, tickets automáticos, bandeja y asignación. Informe de avance (19-10).", ["HU-08", "HU-09", "HU-10", "HU-12", "HU-13", "HU-14", "HU-15"]),
    ("Sprint 6", "Noviembre, semanas 1–2", "Flujo del reponedor en la app (foto, atención y cierre), notificaciones y administración.", ["HU-11", "HU-16", "HU-17", "HU-18", "HU-19", "HU-20", "HU-23", "HU-25", "HU-26"]),
    ("Sprint 7", "Noviembre, semanas 3–4", "Cierre: IA de producto, reportes, pruebas, documentación, despliegue de la demo y presentación final.", ["HU-21", "HU-22", "HU-27", "HU-28", "HU-29", "HU-30"]),
]

# id, epica, rol, quiero, para, criterios, puntos, moscow, valor(1-5), cu, jira, estado
HU = [
    ("HU-00", "EP-08", "equipo de proyecto", "tener el trabajo organizado en un tablero y una Carta Gantt", "saber qué hace cada uno y cuándo", ["Existe el espacio StockEye en Jira con épicas y tareas.", "La Carta Gantt cubre agosto a noviembre."], 3, "Must", 3, "-", "SKT-12, SKT-18, SKT-20", "Hecha"),
    ("HU-01", "EP-08", "equipo de proyecto", "levantar los requisitos con Walmart", "construir lo que el cliente necesita", ["Documento de RF y RNF validado en reunión.", "Casos de uso definidos."], 5, "Must", 5, "-", "SKT-10, SKT-11, SKT-13, SKT-22", "Hecha"),
    ("HU-02", "EP-01", "científico de datos", "un entorno de entrenamiento con GPU dentro del límite de 4 GB de VRAM", "entrenar modelos sin hardware propio", ["Notebook funcionando en Colab o Kaggle.", "Entrenamiento usa menos de 4 GB de VRAM."], 2, "Must", 3, "-", "SKT-17", "Hecha"),
    ("HU-03", "EP-01", "científico de datos", "un dataset propio etiquetado y dividido en entrenamiento, validación y prueba", "entrenar con fotos parecidas a las de las tiendas", ["Imágenes reales y públicas con licencia válida.", "Etiquetas en un formato único.", "División train/val/test documentada."], 8, "Must", 5, "-", "SKT-26 a SKT-36", "Hecha"),
    ("HU-04", "EP-01", "científico de datos", "entrenar un modelo base y medirlo con métricas definidas", "tener un punto de partida comparable", ["Modelo YOLO baseline entrenado.", "Métricas de precisión y falsos positivos/negativos registradas."], 8, "Must", 4, "CU-M02", "SKT-37, SKT-38, SKT-43", "Hecha"),
    ("HU-05", "EP-01", "supervisor", "conocer el % de vacío de cada góndola", "decidir dónde reponer primero", ["El sistema entrega un % de 0 a 100 por foto.", "Se genera una imagen con las zonas vacías marcadas."], 5, "Must", 5, "CU-M02", "SKT-39", "Hecha"),
    ("HU-06", "EP-01", "administrador", "que el análisis de una foto tome máximo 3 segundos en CPU", "no depender de GPU en las tiendas", ["Modelo exportado a ONNX.", "p95 ≤ 3 s por foto en CPU de 4 núcleos."], 8, "Must", 5, "CU-M02", "SKT-40, SKT-41, SKT-42", "Hecha"),
    ("HU-07", "EP-08", "equipo de desarrollo", "un modelo de base de datos con las reglas del negocio", "que los datos sean consistentes aunque cambie la API", ["Migraciones 001–004 aplican sin errores.", "Triggers de ticket, prioridad e historial probados."], 8, "Must", 4, "-", "SKT-14", "Hecha"),
    ("HU-08", "EP-02", "usuario", "iniciar sesión con mi correo y contraseña", "ver solo lo que me corresponde según mi rol", ["Credenciales inválidas muestran error.", "El token se renueva solo.", "Cada rol ve sus pantallas."], 5, "Must", 5, "CU-G01", "SKT-51, SKT-58", "Hecha"),
    ("HU-09", "EP-03", "sistema de cámaras", "enviar fotos periódicas de cada góndola a la API", "detectar quiebres sin intervención humana", ["La cámara se autentica con su API key.", "La foto queda PENDIENTE en la cola.", "Los errores de cámara quedan registrados."], 8, "Must", 5, "CU-M01", "SKT-49", "Hecha"),
    ("HU-10", "EP-03", "sistema", "procesar las fotos en cola con varios workers", "atender varios recintos sin que uno bloquee al resto", ["Dos workers no toman la misma foto.", "Si un worker cae, la foto vuelve a la cola.", "Turnos por recinto."], 8, "Must", 4, "CU-M02", "SKT-49, SKT-56", "Hecha"),
    ("HU-11", "EP-03", "reponedor", "sacar una foto de una góndola desde el celular", "reportar un quiebre que la cámara no ve", ["Puedo elegir la góndola o escanear su QR.", "Veo el % de vacío y la foto anotada.", "Puedo crear el ticket desde el resultado."], 8, "Must", 5, "CU-R02", "SKT-60, SKT-65, SKT-66", "Hecha"),
    ("HU-12", "EP-04", "supervisor", "que se abra un ticket automáticamente cuando el % de vacío supera el umbral", "no tener que revisar las cámaras a mano", ["Ticket con número INC correlativo.", "No se duplica: si ya hay uno abierto, se agrega seguimiento."], 5, "Must", 5, "CU-M03", "SKT-52", "Hecha"),
    ("HU-13", "EP-04", "supervisor", "que la prioridad se calcule según el % de vacío", "atender primero lo más urgente", ["<10 % BAJA, ≥10 % MEDIA, ≥20 % ALTA, ≥40 % CRÍTICA.", "La prioridad sube si empeora."], 3, "Must", 4, "CU-M03", "SKT-52", "Hecha"),
    ("HU-14", "EP-06", "supervisor", "ver una bandeja con los tickets de mi recinto, con filtros y búsqueda", "saber qué está pendiente", ["Contadores por estado.", "Filtros por estado y prioridad.", "Se actualiza en tiempo real."], 5, "Must", 5, "CU-S01", "SKT-61", "Hecha"),
    ("HU-15", "EP-04", "supervisor", "asignar un ticket a un reponedor viendo su carga", "repartir el trabajo de forma justa", ["Solo reponedores activos del mismo recinto.", "Queda registrado en el historial.", "El reponedor recibe aviso."], 5, "Must", 5, "CU-S02", "SKT-61", "Hecha"),
    ("HU-16", "EP-04", "reponedor", "ver mis tickets y marcar cuándo empiezo a atender uno", "organizar mi turno", ["Lista de activos y cerrados hoy.", "Botón Empezar cambia a EN PROGRESO."], 3, "Must", 5, "CU-R01, CU-R03", "SKT-60", "Hecha"),
    ("HU-17", "EP-04", "reponedor", "cerrar el ticket con una foto de verificación", "demostrar que la góndola quedó repuesta", ["Si el % queda bajo el umbral: cierre verificado.", "Si no: comentario obligatorio."], 5, "Must", 5, "CU-R04", "SKT-60", "Hecha"),
    ("HU-18", "EP-04", "supervisor", "cambiar prioridad, editar o cancelar un ticket y ver su historial", "corregir errores del sistema", ["Cancelar exige comentario.", "Todo cambio queda en el historial."], 3, "Should", 3, "CU-S03", "SKT-52", "Hecha"),
    ("HU-19", "EP-04", "reponedor o supervisor", "comentar un ticket", "coordinarnos sin salir del sistema", ["El comentario no puede ir vacío.", "Se avisa a los involucrados."], 2, "Should", 3, "CU-R05", "-", "Hecha"),
    ("HU-20", "EP-05", "reponedor", "recibir una notificación push cuando me asignan un ticket", "enterarme aunque no tenga la app abierta", ["Push por Firebase en Android.", "Web Push en el panel.", "Si Firebase falla, el resto sigue funcionando."], 5, "Should", 4, "CU-G03", "SKT-67", "En curso (falta configurar Firebase en la app)"),
    ("HU-21", "EP-05", "supervisor", "que el sistema sugiera qué producto falta", "pedir el producto correcto a bodega", ["Sugerencia con confianza.", "Se puede corregir a mano.", "Se puede desactivar sin afectar la detección."], 5, "Could", 3, "CU-M04, CU-A06", "-", "Hecha"),
    ("HU-22", "EP-06", "supervisor", "ver reportes de tickets por día y por categoría", "medir el desempeño del recinto", ["Período de 1 a 180 días.", "Indicadores por categoría."], 5, "Should", 4, "CU-S04", "SKT-55, SKT-63", "En curso (falta exportar)"),
    ("HU-23", "EP-07", "administrador", "gestionar recintos, umbral, góndolas y categorías", "adaptar el sistema a cada tienda", ["CRUD de recintos con umbral.", "Góndolas con código y QR."], 5, "Must", 4, "CU-A02, CU-A03", "SKT-53, SKT-54", "Hecha"),
    ("HU-24", "EP-02", "equipo de diseño", "prototipos de las pantallas de la app y del panel", "validar la experiencia antes de programar", ["Mockups de app y panel revisados por el equipo."], 3, "Should", 3, "-", "SKT-15, SKT-57, SKT-64", "Hecha"),
    ("HU-25", "EP-07", "administrador", "registrar cámaras y entregar su API key al capturador", "conectar nuevas cámaras sin tocar código", ["La API key se muestra una sola vez.", "Diagnóstico de cámaras sin señal."], 5, "Must", 4, "CU-A04", "-", "Hecha"),
    ("HU-26", "EP-07", "administrador", "invitar usuarios y subir nuevas versiones del modelo", "mantener el sistema sin ayuda del equipo de desarrollo", ["Clave temporal al invitar.", "Activar y volver a una versión anterior del modelo."], 5, "Must", 4, "CU-A01, CU-A05", "SKT-45, SKT-72", "Hecha"),
    ("HU-27", "EP-08", "equipo de desarrollo", "pruebas automáticas del backend y de las reglas de la base de datos", "no romper nada al hacer cambios", ["22 pruebas de backend en verde.", "Reglas de BD probadas con test_reglas.sql."], 5, "Must", 4, "-", "SKT-69", "Hecha"),
    ("HU-28", "EP-08", "usuario final", "probar los flujos de reponedor y supervisor", "confirmar que el sistema es fácil de usar", ["Se ejecutan los casos del plan de pruebas.", "Se registran hallazgos."], 3, "Must", 4, "-", "SKT-68", "En curso"),
    ("HU-29", "EP-08", "ingeniero de Walmart", "instalar el sistema siguiendo solo un manual", "poder usarlo en otro equipo", ["Docker Compose levanta todo.", "Manual de instalación paso a paso."], 5, "Must", 5, "-", "SKT-70, SKT-71", "Hecha"),
    ("HU-30", "EP-08", "comisión evaluadora", "recibir la documentación final y una presentación", "evaluar el proyecto", ["Documentos según la estructura de Duoc.", "Presentación y video tutorial."], 3, "Must", 4, "-", "SKT-73, SKT-74, SKT-75", "En curso"),
]

if __name__ == "__main__":
    sp = {h[0]: s[0] for s in SPRINTS for h in HU if h[0] in s[3]}
    falt = [h[0] for h in HU if h[0] not in sp]
    print("sin sprint:", falt)
    json.dump(dict(EPICAS=EPICAS, SPRINTS=SPRINTS, HU=HU, SP=sp), open("scrum.json", "w"), ensure_ascii=False, indent=1)
    print("total puntos", sum(h[6] for h in HU))
