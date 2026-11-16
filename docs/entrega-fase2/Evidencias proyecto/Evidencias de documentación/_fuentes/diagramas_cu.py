import os, subprocess, textwrap
from datos import CU

AQUI = os.path.dirname(os.path.abspath(__file__))
IMG = os.path.join(AQUI, "img")
ACTOR = os.path.join(IMG, "actor.png")
CU_BY = {c["id"]: c for c in CU}

FONT = "DejaVu Sans"


def actor(nombre, label=None):
    label = (label or nombre).replace("\\n", "<BR/>")
    return (f'"{nombre}" [shape=plain, label=<<TABLE BORDER="0" CELLSPACING="0" CELLPADDING="1">'
            f'<TR><TD FIXEDSIZE="TRUE" WIDTH="40" HEIGHT="68"><IMG SRC="{ACTOR}" SCALE="TRUE"/></TD></TR>'
            f'<TR><TD><FONT POINT-SIZE="12" FACE="{FONT}">{label}</FONT></TD></TR></TABLE>>];')


def caso(cid):
    c = CU_BY[cid]
    txt = "\\n".join(textwrap.wrap(c["nombre"], 22))
    return (f'"{cid}" [shape=ellipse, style=filled, fillcolor="#eef4ff", color="#2c5aa0", '
            f'label="{cid}\\n{txt}", fontsize=10, fontname="{FONT}", width=2.3];')


def render(nombre, dot):
    ruta = os.path.join(IMG, nombre + ".dot")
    with open(ruta, "w") as f:
        f.write(dot)
    subprocess.run(["dot", "-Tpng", "-Gdpi=170", ruta, "-o", os.path.join(IMG, nombre + ".png")], check=True)


def cabecera(titulo):
    return (f'digraph G {{ rankdir=LR; splines=true; nodesep=0.25; ranksep=1.1; '
            f'fontname="{FONT}"; label="{titulo}"; labelloc=t; fontsize=15; '
            f'edge [arrowhead=none, color="#475569"];\n')


# --- nivel cero ---
paquetes = [
    ("P1", "Gestión de tickets", "CU-R01..R05, CU-S01..S03"),
    ("P2", "Captura y análisis de imágenes", "CU-R02, CU-S05, CU-M01..M03"),
    ("P3", "Reportes y equipo", "CU-S04"),
    ("P4", "Administración", "CU-A01..A06"),
    ("P5", "Notificaciones e IA", "CU-G03, CU-M04"),
    ("P6", "Acceso", "CU-G01, CU-G02"),
]
d = cabecera("StockEye - Diagrama de casos de uso nivel 0")
for a in ["Reponedor", "Supervisor", "Administrador"]:
    d += actor(a) + "\n"
d += actor("Sistema", "Sistema\\n(cámaras / worker)") + "\n"
d += 'subgraph cluster_s { label="Sistema StockEye"; style=rounded; color="#2c5aa0"; fontsize=13;\n'
for pid, nom, cus in paquetes:
    d += (f'"{pid}" [shape=ellipse, style=filled, fillcolor="#eef4ff", color="#2c5aa0", '
          f'label="{nom}\\n({cus})", fontsize=10, fontname="{FONT}", width=3];\n')
d += "}\n"
d += f'"Firebase" [shape=box, style="rounded,filled", fillcolor="#f8fafc", label="«sistema externo»\\nFirebase Cloud\\nMessaging / Web Push", fontsize=10, fontname="{FONT}"];\n'
d += f'"Groq" [shape=box, style="rounded,filled", fillcolor="#f8fafc", label="«sistema externo»\\nProveedor IA (Groq)", fontsize=10, fontname="{FONT}"];\n'
for a, ps in {"Reponedor": ["P1", "P2", "P5", "P6"], "Supervisor": ["P1", "P2", "P3", "P5", "P6"],
              "Administrador": ["P3", "P4", "P6"], "Sistema": ["P2", "P5"]}.items():
    for p in ps:
        d += f'"{a}" -> "{p}";\n'
d += '"P5" -> "Firebase"; "P5" -> "Groq";\n'
d += "}\n"
render("cu_nivel0", d)

# --- por actor ---
grupos = {
    "cu_reponedor": ("Reponedor", "Reponedor", ["CU-G01", "CU-G03", "CU-R01", "CU-R02", "CU-R03", "CU-R04", "CU-R05"],
                     [("CU-R02", "CU-M02", "«include»"), ("CU-R04", "CU-M02", "«include»")], ["CU-M02"]),
    "cu_supervisor": ("Supervisor", "Supervisor", ["CU-G01", "CU-G02", "CU-G03", "CU-S01", "CU-S02", "CU-S03", "CU-R05", "CU-S04", "CU-S05"],
                      [], []),
    "cu_administrador": ("Administrador", "Administrador", ["CU-G01", "CU-G02", "CU-A01", "CU-A02", "CU-A03", "CU-A04", "CU-A05", "CU-A06", "CU-S04", "CU-S05"],
                         [], []),
}
for archivo, (a, lab, cus, rels, extra) in grupos.items():
    d = cabecera(f"StockEye - Casos de uso del {a}")
    d += actor(a, lab) + "\n"
    d += 'subgraph cluster_s { label="Sistema StockEye"; style=rounded; color="#2c5aa0"; fontsize=13;\n'
    for c in cus + extra:
        d += caso(c) + "\n"
    d += "}\n"
    for c in cus:
        d += f'"{a}" -> "{c}";\n'
    for o, t, l in rels:
        if l == "«extend»":
            d += f'"{t}" -> "{o}" [style=dashed, arrowhead=vee, label="{l}", fontsize=9, fontname="{FONT}"];\n'
        else:
            d += f'"{o}" -> "{t}" [style=dashed, arrowhead=vee, label="{l}", fontsize=9, fontname="{FONT}"];\n'
    d += "}\n"
    render(archivo, d)

# sistema: cada componente es un actor
d = cabecera("StockEye - Casos de uso de los actores de sistema")
comp = [("Capturador", "Capturador\\n(cámaras IP)", "CU-M01"), ("Worker", "Worker de\\ninferencia", "CU-M02"),
        ("BaseDatos", "Base de datos\\n(PostgreSQL)", "CU-M03"), ("ServicioIA", "Servicio de IA", "CU-M04"),
        ("Notificador", "Notificador", "CU-G03")]
for n, l, _ in comp:
    d += actor(n, l) + "\n"
d += 'subgraph cluster_s { label="Sistema StockEye"; style=rounded; color="#2c5aa0"; fontsize=13;\n'
for _, _, c in comp:
    d += caso(c) + "\n"
d += "}\n"
for n, _, c in comp:
    d += f'"{n}" -> "{c}";\n'
d += f'"CU-M03" -> "CU-M04" [style=dashed, arrowhead=vee, label="«extend»\\n(IA activa)", fontsize=9, fontname="{FONT}", dir=back, constraint=false];\n'
d += f'"CU-M03" -> "CU-G03" [style=dashed, arrowhead=vee, label="«include»", fontsize=9, fontname="{FONT}", constraint=false];\n'
d += f'"Groq" [shape=box, style="rounded,filled", fillcolor="#f8fafc", label="«sistema externo»\\nProveedor IA (Groq)", fontsize=10, fontname="{FONT}"];\n'
d += f'"Firebase" [shape=box, style="rounded,filled", fillcolor="#f8fafc", label="«sistema externo»\\nFirebase / Web Push", fontsize=10, fontname="{FONT}"];\n'
d += '"CU-M04" -> "Groq"; "CU-G03" -> "Firebase";\n{rank=same; "Capturador"; "Worker"; "BaseDatos"; "ServicioIA"; "Notificador";}\n}\n'
render("cu_sistema", d)
print("ok")
