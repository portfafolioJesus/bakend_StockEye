import json, re, subprocess, os
from bd_desc import TABLAS, desc, TIPOS_ENUM
cols = [l.rstrip("\n").split("|", 4) for l in open("/var/tmp/pgse/cols.txt")]
cons = [l.rstrip("\n").split("|", 3) for l in open("/var/tmp/pgse/cons.txt")]
counts = dict(l.strip().split("|") for l in open("/var/tmp/pgse/counts.txt"))
pk, fk, uk, ck = {}, {}, {}, {}
for t, typ, name, d in cons:
    cs = [c.strip() for c in re.search(r"\(([^)]*)\)", d).group(1).split(",")] if typ in "pfu" else []
    if typ == "p": pk[t] = cs
    elif typ == "u": uk.setdefault(t, []).append(cs)
    elif typ == "f":
        ref = re.search(r"REFERENCES (\w+)\(([^)]*)\)", d)
        fk.setdefault(t, []).append((cs, ref.group(1), d))
    else: ck.setdefault(t, []).append(d)
esquema = {}
falta = []
for t, c, tipo, nul, dflt in cols:
    claves = []
    if c in pk.get(t, []): claves.append("PK")
    for cs, ref, _ in fk.get(t, []):
        if c in cs: claves.append(f"FK→{ref}")
    for cs in uk.get(t, []):
        if c in cs: claves.append("UQ")
    dflt = re.sub(r"::[\w ]+", "", dflt)
    if dflt.startswith("nextval"): dflt = "autoincremental"
    d = desc(t, c)
    if tipo in TIPOS_ENUM: d = (d + " " if d else "") + f"Valores: {TIPOS_ENUM[tipo]}." if TIPOS_ENUM[tipo] not in d else d
    if not d: falta.append((t, c))
    esquema.setdefault(t, []).append(dict(col=c, tipo=tipo.replace("timestamp with time zone", "timestamptz").replace("character", "char"), nulo="Sí" if nul == "YES" else "No", default=dflt, claves=", ".join(dict.fromkeys(claves)), desc=d))
print("sin descripcion:", falta)
json.dump(dict(esquema=esquema, ck=ck, fk={t: [(cs, r) for cs, r, _ in v] for t, v in fk.items()}, counts=counts, tablas=TABLAS), open("bd.json", "w"), ensure_ascii=False, indent=1)

# ---- modelo relacional (todas las columnas) ----
GR = {"Maestros": "#e3f2fd", "Detección": "#f3e5f5", "Tickets": "#e8f5e9", "IA y notificaciones": "#fff3e0"}
F = "DejaVu Sans"
def nodo(t, completo=True):
    color = GR[TABLAS[t][0]]
    filas = f'<TR><TD BGCOLOR="#1F3A68" COLSPAN="2"><FONT COLOR="white" FACE="{F}"><B>{t}</B></FONT></TD></TR>'
    for c in esquema[t]:
        k = c["claves"]
        if not completo and not k: continue
        
        tag = ("PK " if "PK" in k else "") + ("FK" if "FK" in k else "")
        nombre = f"<B>{c['col']}</B>" if "PK" in k else (f"<I>{c['col']}</I>" if "FK" in k else c["col"])
        if completo:
            filas += f'<TR><TD ALIGN="LEFT" BGCOLOR="{color}"><FONT FACE="{F}" POINT-SIZE="9">{tag.strip()} {nombre}</FONT></TD><TD ALIGN="LEFT" BGCOLOR="{color}"><FONT FACE="{F}" POINT-SIZE="8" COLOR="#555555">{c["tipo"]}</FONT></TD></TR>'
        else:
            filas += f'<TR><TD ALIGN="LEFT" COLSPAN="2" BGCOLOR="{color}"><FONT FACE="{F}" POINT-SIZE="9">{tag.strip()} {nombre}</FONT></TD></TR>'
    return f'"{t}" [shape=plain, label=<<TABLE BORDER="0" CELLBORDER="1" CELLSPACING="0" CELLPADDING="3">{filas}</TABLE>>];\n'

def grafo(nombre, completo, rankdir="LR"):
    d = f'digraph G {{ rankdir={rankdir}; nodesep=0.35; ranksep=0.9; splines=true; fontname="{F}"; edge [color="#64748b", arrowhead=crow, arrowtail=tee, dir=both];\n'
    for t in esquema:
        d += nodo(t, completo)
    vistos = set()
    for t, lst in fk.items():
        for cs, ref, _ in lst:
            key = (t, ref)
            if key in vistos: continue
            vistos.add(key)
            d += f'"{ref}" -> "{t}" [tooltip="{",".join(cs)}"];\n'
    d += "}\n"
    p = f"img/{nombre}.dot"; open(p, "w").write(d)
    subprocess.run(["dot", "-Tpng", "-Gdpi=130", p, "-o", f"img/{nombre}.png"], check=True)
    subprocess.run(["dot", "-Tsvg", p, "-o", f"img/{nombre}.svg"], check=True)
grafo("bd_modelo_relacional", True, "TB")
grafo("bd_modelo_relacional_claves", False, "TB")
print("ok")
