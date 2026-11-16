import json
T = """10|Reuniones con el cliente|Listo|Claudio Galiano
11|Definición del documento de especificaciones funcionales|Listo|Claudio Galiano
12|Crear tablero de seguimiento en Jira|En curso|Claudio Galiano
13|Definición de los casos de uso|Listo|Claudio Galiano
14|Diseño de la arquitectura de la base de datos|Por hacer|Jesús González
15|Creación de prototipos de interfaz de usuario (UI/UX)|Listo|Claudio Galiano
16|Definición de tecnologías|Listo|Claudio Galiano
17|Configuración del entorno de entrenamiento (Colab/Kaggle, límites de VRAM)|Listo|Ignacio Ruz
18|Creación carta gantt|Listo|Claudio Galiano
19|Recepción del caso (KickOff Walmart)|Listo|Claudio Galiano
20|Organización del equipo|Listo|Claudio Galiano
21|Definición de objetivos y alcance del proyecto|En curso|Claudio Galiano
22|Levantamiento de requerimientos funcionales y no funcionales|Listo|Claudio Galiano
23|Documento preliminar de presentación del proyecto|Listo|Claudio Galiano
24|Definición del criterio de éxito (umbral 30%)|Listo|Ignacio Ruz
25|Análisis y validación de requerimientos con criterios de Walmart|Por hacer|Claudio Galiano
26|Revisión de imágenes reales|En curso|Ignacio Ruz
27|Investigación de datasets públicos de retail/góndolas|Listo|Ignacio Ruz
28|Validación de licencias de datasets open source|Listo|Ignacio Ruz
29|Definición del formato estándar de bounding box|Listo|Ignacio Ruz
30|Documentación de hallazgos del análisis exploratorio|Listo|Ignacio Ruz
31|Recolección adicional de imágenes propias en terreno|Listo|Claudio Galiano
32|Etiquetado de espacios vacíos por nivel de góndola|En curso|Ignacio Ruz
33|División del dataset en entrenamiento, validación y prueba|Listo|Ignacio Ruz
34|Aplicación de aumento de datos (data augmentation)|Listo|Ignacio Ruz
35|Normalización de imágenes|Listo|Ignacio Ruz
36|Validación de calidad y consistencia del dataset etiquetado|Listo|Ignacio Ruz
37|Investigación de enfoques: CV clásico vs. YOLO|Listo|Ignacio Ruz
38|Entrenamiento del modelo YOLO baseline|Listo|Ignacio Ruz
39|Cálculo del porcentaje de espacio libre por nivel/repisa|En curso|Ignacio Ruz
40|Ajuste de hiperparámetros y reentrenamiento|En curso|Ignacio Ruz
41|Validación de tiempos de inferencia (2 a 5 s por imagen)|En curso|Ignacio Ruz
42|Empaquetado del modelo|En curso|Ignacio Ruz
43|Definición de métricas internas|Listo|Ignacio Ruz
44|Pruebas internas del modelo con dataset propio|En curso|Ignacio Ruz
45|Entrega del modelo empaquetado a Walmart|En curso|Ignacio Ruz
46|Análisis del reporte de desempeño y mapa de errores|En curso|Ignacio Ruz
47|Ajuste del modelo según hallazgos del reporte|En curso|Ignacio Ruz
48|Documentación de resultados y decisiones de ajuste|En curso|Ignacio Ruz
49|Backend: endpoint de inferencia y cola de trabajos|En curso|Jesús González
50|Backend: subir el código al repositorio|Por hacer|Jesús González
51|Backend: login con roles|Por hacer|Jesús González
52|Backend: alertas con estado, asignación y prioridad|Por hacer|Jesús González
53|Backend: guardar umbrales del semáforo|Por hacer|Jesús González
54|Backend: ubicación de cada góndola|Por hacer|Jesús González
55|Backend: datos para el reporte de desempeño|Por hacer|Jesús González
56|Integración del modelo entrenado con el backend|Por hacer|Ignacio Ruz
57|App: base del proyecto en Kotlin y diseño|Listo|Claudio Galiano
58|App: iniciar sesión con roles (CU-G01)|En curso|Claudio Galiano
59|App: pestaña Pasillos con semáforo (CU-R01, CU-S01)|En curso|Claudio Galiano
60|App: alertas, tomar y marcar lista (CU-R02 a CU-R04)|En curso|Claudio Galiano
61|App: asignar y priorizar alertas (CU-S02)|En curso|Claudio Galiano
62|App: ajustar umbrales del semáforo (CU-S03)|En curso|Claudio Galiano
63|App: resumen y reporte de desempeño (CU-S04)|En curso|Claudio Galiano
64|App: perfil de usuario y lista de tareas|Listo|Claudio Galiano
65|App: conectar a la API del backend|Por hacer|Claudio Galiano
66|App: mostrar la foto analizada de la góndola|Por hacer|Claudio Galiano
67|Notificaciones push al reponedor (Firebase)|Por hacer|Jesús González
68|Pruebas de usuario con los flujos de reponedor y supervisor|Por hacer|Jesús González
69|Pruebas unitarias y de integración del sistema completo|Por hacer|Jesús González
70|Documentación técnica (manual de instalación y ejecución)|Por hacer|Jesús González
71|Preparación del entorno de despliegue/demo|Por hacer|Jesús González
72|Empaquetado final de la solución (modelo + app)|Por hacer|Jesús González
73|Actualización final del repositorio GitHub|Por hacer|Claudio Galiano
74|Elaboración de la documentación final del proyecto|Por hacer|Claudio Galiano
75|Preparación de la presentación final ante la comisión|Por hacer|Claudio Galiano"""
EP = [(1, "Análisis de requisitos", 10, 13), (2, "Diseño del sistema", 14, 23), (3, "Comprensión del negocio", 24, 25), (4, "Comprensión de los datos", 26, 30), (5, "Preparación de los datos", 31, 36), (6, "Modelado", 37, 42), (7, "Evaluación del modelo", 43, 48), (8, "Codificación", 49, 70), (9, "Despliegue y cierre", 71, 75)]
tareas = []
for l in T.split("\n"):
    n, s, e, a = l.split("|"); n = int(n)
    ep = next(f"SKT-{k} {nom}" for k, nom, a1, b1 in EP if a1 <= n <= b1)
    tareas.append(dict(key=f"SKT-{n}", resumen=s, estado=e, resp=a, epica=ep))
json.dump(tareas, open("jira.json", "w"), ensure_ascii=False, indent=1)
from collections import Counter
print(len(tareas), Counter(t["estado"] for t in tareas))
