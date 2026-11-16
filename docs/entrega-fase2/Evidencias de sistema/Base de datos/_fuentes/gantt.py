import openpyxl, sys
from openpyxl.styles import PatternFill
SRC, DST = sys.argv[1], sys.argv[2]
wb = openpyxl.load_workbook(SRC)
v1 = wb.active; v1.title = "Iteración 1"
ws = wb.copy_worksheet(v1); ws.title = "Iteración 2 (15-11)"
wb.move_sheet(ws, offset=-1); wb.active = 0
AMA = PatternFill("solid", fgColor="FFFFE599"); NADA = PatternFill(fill_type=None)
ws["B1"] = "Carta Gantt caso Walmart · Iteración 2 (actualizada al 15-11-2026)"
NUEVAS = {
 49: ("Backend v2: API de tickets, ingesta de fotos y cola de análisis", "Jesús González", "x", (40, 51)),
 50: ("Panel web (React) para supervisor y administrador", "Jesús González", "x", (44, 55)),
 51: ("App Android del reponedor: foto, tickets y cierre verificado", "Kevin Galiano y Jesús González", "x", (44, 55)),
 52: ("Integración del modelo SegFormer (ONNX) con el worker de inferencia", "Jesús González y Ignacio Ruz", "x", (44, 49)),
 53: ("Notificaciones push (Firebase / Web Push) e IA de producto", "Jesús González", "/", (50, 55)),
 54: ("Pruebas unitarias, de reglas de BD y de usuario", "Jesús González y todo el equipo", "/", (54, 59)),
 55: ("Documentación técnica (manual de instalación y ejecución)", "Jesús González", "x", (52, 57)),
 56: ("Preparación del entorno de despliegue/demo (Docker Compose)", "Jesús González", "/", (56, 59)),
 57: ("Empaquetado final de la solución (modelo + app Android + panel web)", "Jesús González y Ignacio Ruz", "/", (57, 60)),
 58: ("Actualización final del repositorio GitHub", "Todo el equipo", "/", (58, 60)),
 59: ("Documentación final del proyecto (CU, SCRUM, base de datos, manuales)", "Kevin Galiano", "/", (54, 59)),
 60: ("Presentación final y video tutorial ante la comisión evaluadora", "Kevin Galiano", None, (59, 63)),
}
for r, (act, resp, est, (a, b)) in NUEVAS.items():
    ws.cell(r, 3).value = act; ws.cell(r, 4).value = resp; ws.cell(r, 5).value = est
    for i in range(1, 64):  # deja la col E (indice 0) para el estado
        c = ws.cell(r, 5 + i)
        if c.fill.fill_type and c.fill.fgColor.rgb == "FFFFE599": c.fill = NADA
    for i in range(max(a, 1), b + 1): ws.cell(r, 5 + i).fill = AMA
for r, est in {11: "x", 12: "x", 13: "x", 14: "x", 15: "x", 21: "x", 25: "/"}.items():
    ws.cell(r, 5).value = est
ws["C3"] = "Jesús González - Kevin Galiano - Ignacio Ruz"
ws["C7"] = "hechas/en proceso="
ws["D7"] = '=COUNTIF(E10:E60,"x")+COUNTIF(E10:E60,"/")'
ws["D8"] = "=COUNTA(C10:C60)"
ws["C5"] = "Estado (columna E): x = hecha · / = en proceso · vacío = pendiente"
wb.save(DST)
x = sum(1 for r in range(10, 61) if ws.cell(r, 5).value == "x"); p = sum(1 for r in range(10, 61) if ws.cell(r, 5).value == "/")
print("hechas", x, "en proceso", p, "total", sum(1 for r in range(10, 61) if ws.cell(r, 3).value))
