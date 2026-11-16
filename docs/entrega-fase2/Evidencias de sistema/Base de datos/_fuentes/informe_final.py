import sys, copy
import docx
from docx.shared import Pt, Cm, RGBColor
from docx.enum.text import WD_COLOR_INDEX

SRC, DST, IMG = sys.argv[1], sys.argv[2], sys.argv[3]
d = docx.Document(SRC)
AZUL = RGBColor(0x1F, 0x3A, 0x68)

def limpiar(cell):
    for p in cell.paragraphs[1:]:
        p._element.getparent().remove(p._element)
    for t in cell.tables:
        t._element.getparent().remove(t._element)
    p0 = cell.paragraphs[0]
    p0.text = ""
    if p0._p.pPr is not None:
        p0._p.remove(p0._p.pPr)
    for r in list(p0.runs): r._r.getparent().remove(r._r)
    return cell

def run(p, texto, bold=False, italic=False, size=10, color=None, resaltar=False):
    r = p.add_run(texto); r.bold = bold; r.italic = italic; r.font.size = Pt(size)
    if color: r.font.color.rgb = color
    if resaltar: r.font.highlight_color = WD_COLOR_INDEX.YELLOW
    return r

def llenar(cell, bloques):
    limpiar(cell)
    primero = True
    for b in bloques:
        p = cell.paragraphs[0] if primero else cell.add_paragraph()
        if p._p.pPr is not None and p._p.pPr.numPr is not None:
            p._p.pPr.remove(p._p.pPr.numPr)
        p.alignment = 0
        primero = False
        p.paragraph_format.space_after = Pt(4)
        tipo = b[0]
        if tipo == "h":
            p.paragraph_format.space_before = Pt(6); run(p, b[1], bold=True, size=10.5, color=AZUL)
        elif tipo == "p":
            run(p, b[1])
        elif tipo == "pb":  # parrafo con etiqueta en negrita
            run(p, b[1], bold=True); run(p, b[2])
        elif tipo == "li":
            p.paragraph_format.left_indent = Cm(0.5); p.paragraph_format.first_line_indent = Cm(-0.35)
            run(p, "• ");
            if len(b) == 3: run(p, b[1], bold=True); run(p, b[2])
            else: run(p, b[1])
        elif tipo == "img":
            run(p, "").add_picture(b[1], width=Cm(b[2]))
            c = cell.add_paragraph(); run(c, b[3], italic=True, size=8.5, color=RGBColor(0x55, 0x55, 0x55))
        elif tipo == "nota":
            run(p, b[1], italic=True, size=9, resaltar=True)

t1, t2 = d.tables[1], d.tables[2]
llenar(t1.rows[0].cells[1], [("p", "StockEye: detección de quiebres de stock en góndolas con visión por computador (caso Walmart Chile)")])
llenar(t1.rows[1].cells[1], [("li", "Desarrollo e implementación de soluciones informáticas."), ("li", "Gestión de proyectos informáticos y arquitectura de software."), ("li", "Análisis y solución de problemas complejos.")])
llenar(t1.rows[2].cells[1], [("li", "Diseño, desarrollo e implementación de soluciones informáticas complejas."), ("li", "Capacidad analítica y resolución de problemas de ingeniería."), ("li", "Ética profesional y cumplimiento normativo.")])

# 1. Relevancia
llenar(t2.rows[1].cells[1], [
    ("p", "En los supermercados de Walmart Chile un quiebre de stock (un producto que se acaba en la góndola) significa ventas perdidas y clientes que no encuentran lo que buscan. Hoy esos quiebres se detectan a simple vista: un reponedor o supervisor recorre los pasillos, y en una tienda grande un vacío puede pasar horas sin reponerse."),
    ("pb", "Dónde se ubica: ", "en salas de venta reales de Walmart Chile, que ya tienen cámaras de seguridad instaladas. Sus imágenes son difíciles: ángulos tipo ojo de pez, reflejos en estantes metálicos, vapor en refrigeradores y zonas ciegas."),
    ("pb", "A quiénes afecta: ", "a los reponedores (que no saben qué reponer primero), a los supervisores de sala (que no tienen visibilidad del estado de las góndolas), a la empresa (ventas perdidas) y a los clientes."),
    ("pb", "Relevancia para la profesión: ", "el proyecto combina inteligencia artificial aplicada (visión por computador), desarrollo de software full stack, bases de datos y despliegue reproducible, con restricciones reales entregadas por un cliente industrial: hardware limitado, tiempo de respuesta y evaluación con un dataset oculto."),
    ("pb", "Aporte de valor: ", "StockEye transforma las fotos de las cámaras (o del celular del reponedor) en tickets de reposición con prioridad automática, responsable y cierre verificado con una foto. El supervisor ve en tiempo real qué falta y quién lo está reponiendo, y la empresa obtiene trazabilidad e indicadores de desempeño por recinto y categoría."),
])
# 2. Objetivos
llenar(t2.rows[2].cells[1], [
    ("pb", "Objetivo general: ", "diseñar e implementar un sistema de visión por computador integrado a una plataforma web y móvil que detecte automáticamente los quiebres de stock en las góndolas de Walmart Chile y gestione su reposición, a partir de imágenes fijas de las cámaras de sala y de fotos tomadas por los reponedores."),
    ("h", "Objetivos específicos"),
    ("li", "Construir y etiquetar un dataset propio de góndolas con fotos reales tomadas en terreno, complementado con datasets públicos con licencia válida."),
    ("li", "Entrenar y evaluar un modelo que calcule el porcentaje de espacio vacío de una góndola, cumpliendo las restricciones de hardware (≤ 4 GB de VRAM en entrenamiento) y de tiempo (≤ 3 s por imagen en CPU)."),
    ("li", "Implementar una API y una base de datos que reciban las fotos, las analicen en cola y abran tickets automáticamente cuando el vacío supera el umbral del recinto."),
    ("li", "Desarrollar una app Android para reponedores y un panel web para supervisores y administradores que permitan asignar, atender y cerrar tickets con foto de verificación."),
    ("li", "Empaquetar y documentar la solución para que pueda instalarse en otro equipo siguiendo solo un manual (Docker Compose)."),
])
# 3. Metodología
llenar(t2.rows[3].cells[1], [
    ("p", "Se usó un enfoque híbrido: CRISP-DM para el modelo de visión y Scrum (con tablero Kanban en Jira) para el producto."),
    ("pb", "CRISP-DM: ", "ordenó el trabajo del modelo en sus fases: comprensión del negocio (kickoff con Walmart y criterio de éxito), comprensión de los datos (análisis de imágenes reales y datasets públicos), preparación (etiquetado, división por series, aumento de datos), modelado (YOLO baseline y luego segmentación SegFormer), evaluación (métricas internas y tiempos) y despliegue (exportación a ONNX)."),
    ("pb", "Scrum: ", "el producto se dividió en 8 épicas y 31 historias de usuario priorizadas con MoSCoW y valor/esfuerzo, trabajadas en 8 sprints de 2 semanas (agosto a noviembre). El largo del sprint coincide con el ciclo de evaluación de Walmart (~2 semanas), así cada sprint termina con algo revisable por el cliente o el docente."),
    ("pb", "Roles: ", "Product Owner José Larraín (Walmart, área de IA); docente guía Arturo Vargas; Scrum Master Claudio Galiano; equipo de desarrollo Jesús González (backend, base de datos, panel web), Ignacio Ruz (datos y modelo) y Claudio Galiano (app móvil y UI/UX)."),
    ("pb", "Pertinencia: ", "un modelo de IA necesita experimentación iterativa sobre los datos, y CRISP-DM está pensado justamente para eso. El sistema que lo rodea, en cambio, se beneficia de entregas cortas y de priorizar lo que aporta valor al cliente, que es lo que ofrece Scrum. Combinarlos permitió avanzar en paralelo en el modelo y en la aplicación sin que uno bloqueara al otro."),
])
# 4. Desarrollo
llenar(t2.rows[4].cells[1], [
    ("h", "Etapas"),
    ("li", "Sprints 0–1 (agosto): ", "kickoff con Walmart, organización del equipo, Carta Gantt, tablero, requisitos funcionales y no funcionales, casos de uso y matriz de riesgos."),
    ("li", "Sprints 2–3 (septiembre): ", "análisis de imágenes, investigación y validación de licencias de datasets, fotos propias en terreno, etiquetado y primer modelo YOLO baseline."),
    ("li", "Sprint 4 (octubre, 1.ª quincena): ", "cambio a segmentación (SegFormer MiT-b1) y exportación a ONNX; diseño de la base de datos y prototipos de interfaz."),
    ("li", "Sprint 5 (octubre, 2.ª quincena): ", "núcleo del sistema: login con roles, recepción de fotos, cola de análisis con varios workers, tickets automáticos con prioridad, bandeja y asignación. Informe de avance (19-10)."),
    ("li", "Sprint 6 (noviembre, 1.ª quincena): ", "app Android del reponedor (foto, atención y cierre verificado), notificaciones push y Web Push, administración de recintos, cámaras, usuarios y versiones del modelo."),
    ("li", "Sprint 7 (noviembre, 2.ª quincena): ", "IA de producto (sugerencia del producto faltante), reportes, pruebas, documentación, despliegue de la demo y presentación."),
    ("h", "Facilitadores"),
    ("li", "Un equipo complementario (datos, backend y diseño) y comunicación constante."),
    ("li", "Retroalimentación del cliente y del docente en cada hito."),
    ("li", "Herramientas gratuitas: Google Colab/Kaggle para entrenar, GitHub, Jira y Docker."),
    ("h", "Dificultades"),
    ("li", "Pocas imágenes reales y muy variables (ángulos, reflejos, iluminación)."),
    ("li", "Vacíos pequeños y repisas casi vacías difíciles de detectar; series de fotos parecidas mezcladas entre entrenamiento y validación."),
    ("li", "Cambio de alcance a mitad del semestre: una alerta sola no asegura que alguien reponga."),
    ("li", "Coordinar el desarrollo del modelo y de la aplicación en paralelo con un equipo de tres personas."),
    ("h", "Ajustes realizados"),
    ("li", "Datos: ", "fotos propias en terreno (2 y 5 de octubre), división del dataset por series completas, recortes centrados y mosaicos para vacíos pequeños."),
    ("li", "Modelo: ", "se pasó de cajas (YOLO) a segmentación por píxel (SegFormer), que entrega un % de vacío más preciso, y se exportó a ONNX para correr en CPU en 1,1 a 2,0 s por foto."),
    ("li", "Producto: ", "la alerta con semáforo evolucionó a un ticket con estados, prioridad automática, historial y cierre verificado con foto; el umbral fijo de 30 % pasó a ser configurable por recinto."),
    ("li", "Gestión: ", "se ordenó el trabajo en sprints de 2 semanas y se separaron carriles por área en Jira."),
])
# 5. Evidencias
E = lambda n: f"{IMG}/{n}"
llenar(t2.rows[5].cells[1], [
    ("p", "Todas las evidencias están en el repositorio del sistema (github.com/portfafolioJesus/bakend_StockEye, carpeta docs/entrega-fase2) y en la carpeta del curso:"),
    ("li", "Documentación: ", "listado de RF/RNF y casos de uso, diagramas de casos de uso (nivel 0 y por actor), planillas de CU, diagramas de actividad, documentación SCRUM (análisis del caso, épicas, sprints, historias y priorización)."),
    ("li", "Base de datos: ", "diccionario de datos, modelo lógico, modelo relacional, script para poblar tablas (probado en PostgreSQL 16) y nota sobre NoSQL."),
    ("li", "Sistema: ", "código en GitHub (backend, panel web, app Android, capturador), APK, ambiente de desarrollo y video tutorial."),
    ("li", "Anexos: ", "instructivo de instalación, manual de usuario, plan de pruebas (25 pruebas automáticas, 8 reglas de base de datos aprobadas, rendimiento ≤ 3 s) y Carta Gantt."),
    ("img", E("cu_nivel0.png"), 11.5, "Figura 1. Diagrama de casos de uso nivel 0."),
    ("img", E("mock_bandeja.png"), 11.5, "Figura 2. Bandeja de tickets del panel web (supervisor)."),
    ("img", E("mock_app.png"), 5.0, "Figura 3. App del reponedor: resultado del análisis de una foto."),
    ("img", E("scrum_velocidad.png"), 12.0, "Figura 4. Puntos de historia por sprint y burndown del backlog."),
])
# 6. Intereses
llenar(t2.rows[6].cells[1], [
    ("nota", "Borrador: cada integrante debe revisar y ajustar su párrafo con sus propias palabras."),
    ("pb", "Claudio Galiano: ", "al comenzar mis intereses estaban en la gestión de proyectos y el diseño de experiencia de usuario. En el proyecto asumí la coordinación (Carta Gantt, tablero en Jira, documentación y metodología) y el diseño y desarrollo de la app del reponedor, lo que confirmó ese interés y me acercó al desarrollo frontend móvil. Me proyecto en roles de jefe de proyecto o diseñador UX/UI en equipos de desarrollo, y quiero profundizar en metodologías ágiles y en diseño de producto."),
    ("pb", "Jesús González: ", "mi interés era proyectarme hacia roles de ingeniería de software más exigentes, profundizando en frontend y backend e integración de sistemas complejos. En StockEye construí la API, la base de datos, el panel web y el despliegue con Docker, integrando un modelo de IA en un sistema real. Mis intereses se mantienen y se fortalecieron hacia la arquitectura de software y el backend."),
    ("pb", "Ignacio Ruz: ", "mis intereses apuntaban a la ciencia de datos y el backend. Trabajar con imágenes reales, etiquetado, entrenamiento y evaluación de modelos con restricciones de hardware me permitió conocer el ciclo completo de un modelo de visión hasta su despliegue. Quiero seguir profundizando en machine learning aplicado y en llevar modelos a producción (MLOps)."),
])
d.save(DST)
print("ok")
