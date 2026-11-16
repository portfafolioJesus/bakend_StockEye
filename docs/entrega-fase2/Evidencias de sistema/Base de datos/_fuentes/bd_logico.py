import subprocess
F = "DejaVu Sans"
ENT = {
 "Recinto": ["código", "nombre", "umbral de vacío"], "Usuario": ["email", "nombre", "rol"],
 "Categoría": ["código", "nombre"], "Góndola": ["código", "pasillo"], "Cámara": ["código", "URL", "intervalo"],
 "Imagen": ["origen", "archivo", "estado"], "Modelo IA": ["versión", "familia", "activo"],
 "Predicción": ["% vacío", "supera umbral"], "Detección": ["clase", "caja", "confianza"],
 "Ticket": ["número", "estado", "prioridad", "% vacío"], "Comentario": ["texto"], "Historial ticket": ["estado anterior/nuevo"],
 "Análisis IA": ["productos sugeridos"], "Notificación": ["tipo", "leída"], "Dispositivo push": ["token"], "Tarea": ["tipo", "estado"],
}
REL = [
 ("Recinto", "Góndola", "tiene", "1", "N"), ("Recinto", "Usuario", "trabaja en", "N", "M"),
 ("Categoría", "Góndola", "clasifica", "1", "N"), ("Góndola", "Cámara", "es enfocada por", "1", "N"),
 ("Cámara", "Imagen", "captura", "1", "N"), ("Usuario", "Imagen", "sube", "1", "N"), ("Góndola", "Imagen", "aparece en", "1", "N"),
 ("Imagen", "Predicción", "se analiza en", "1", "N"), ("Modelo IA", "Predicción", "genera", "1", "N"),
 ("Predicción", "Detección", "contiene", "1", "N"), ("Góndola", "Ticket", "origina", "1", "N"),
 ("Usuario", "Ticket", "atiende", "1", "N"), ("Ticket", "Imagen", "tiene evidencia", "N", "M"),
 ("Ticket", "Comentario", "recibe", "1", "N"), ("Usuario", "Comentario", "escribe", "1", "N"),
 ("Ticket", "Historial ticket", "registra", "1", "N"), ("Ticket", "Análisis IA", "se enriquece con", "1", "N"),
 ("Usuario", "Notificación", "recibe", "1", "N"), ("Usuario", "Dispositivo push", "registra", "1", "N"), ("Recinto", "Tarea", "agrupa", "1", "N"),
]
d = f'graph G {{ layout=neato; overlap=false; sep="+18"; splines=true; fontname="{F}"; node [fontname="{F}"]; edge [fontname="{F}", fontsize=10, color="#64748b"];\n'
d = f'graph G {{ rankdir=TB; nodesep=0.5; ranksep=0.8; fontname="{F}"; node [fontname="{F}"]; edge [fontname="{F}", fontsize=10, color="#64748b", fontcolor="#334155"];\n'
for e, at in ENT.items():
    filas = "".join(f'<TR><TD ALIGN="LEFT"><FONT POINT-SIZE="9">{a}</FONT></TD></TR>' for a in at)
    d += f'"{e}" [shape=plain, label=<<TABLE BORDER="1" CELLBORDER="0" CELLSPACING="0" CELLPADDING="3" BGCOLOR="#eef4ff" COLOR="#1F3A68"><TR><TD BGCOLOR="#1F3A68"><FONT COLOR="white"><B>{e}</B></FONT></TD></TR>{filas}</TABLE>>];\n'
for a, b, v, ca, cb in REL:
    d += f'"{a}" -- "{b}" [label="{v}", taillabel="{ca}", headlabel="{cb}", labeldistance=1.6];\n'
d += "}\n"
open("img/bd_modelo_logico.dot", "w").write(d)
subprocess.run(["dot", "-Tpng", "-Gdpi=140", "img/bd_modelo_logico.dot", "-o", "img/bd_modelo_logico.png"], check=True)
print("ok")
