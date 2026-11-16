import openpyxl, datetime, sys
from copy import copy
from datos import CU
SRC = sys.argv[1]; DST = sys.argv[2]
wb = openpyxl.load_workbook(SRC)
r1 = wb["RESUMEN"]; ws = wb["RESUMEN 2"]
ws.title = "Avance final 15-11"
r1.title = "Avance 22-09"

C, J, R = "Claudio Galiano", "Jesús González", "Ignacio Ruz"
ENC = {"CU-G01": f"{C}, {J}", "CU-G02": J, "CU-G03": J,
       "CU-R01": C, "CU-R02": C, "CU-R03": C, "CU-R04": f"{C}, {J}", "CU-R05": C,
       "CU-S01": f"{C}, {J}", "CU-S02": J, "CU-S03": J, "CU-S04": J, "CU-S05": J,
       "CU-A01": R, "CU-A02": R, "CU-A03": R, "CU-A04": J, "CU-A05": J, "CU-A06": J,
       "CU-M01": f"{R}, {J}", "CU-M02": R, "CU-M03": J, "CU-M04": J}
PROB = {"CU-G03": "La app necesita el archivo google-services.json del proyecto Firebase para recibir push en el celular.",
        "CU-S04": "Falta exportar el reporte a Excel o PDF.",
        "CU-M01": "Probado con cámara simulada y carpeta de entradas; falta probar con cámaras reales de Walmart."}

# encabezado
for row in range(1, 6):
    ws.row_dimensions[row].height = r1.row_dimensions[row + 1].height
ws["A1"] = r1["A2"].value; ws["B1"] = "Detección de quiebres de stock en góndolas (Walmart Chile) – StockEye"
ws["A2"] = "Integrantes:"; ws["B2"] = "1.- Ignacio Ruz"; ws["B3"] = "2.- Jesús González"; ws["B4"] = "3.- Claudio Galiano"
for cell in ("A1", "A2"):
    ws[cell].font = copy(r1["A2"].font)
for col in "ABCDEFGH":
    ws.column_dimensions[col].width = r1.column_dimensions[col].width or 18
    h = ws[f"{col}5"]; s = r1[f"{col}6"]
    h.font, h.fill, h.border, h.alignment = copy(s.font), copy(s.fill), copy(s.border), copy(s.alignment)
ws.column_dimensions["A"].width = 20; ws.column_dimensions["G"].width = 55; ws.column_dimensions["H"].width = 45
ws.column_dimensions["C"].width = 34; ws.column_dimensions["D"].width = 24; ws.column_dimensions["E"].width = 28

fecha = datetime.datetime(2026, 11, 15)
for i, c in enumerate(CU):
    row = 6 + i
    vals = [fecha, c["id"], c["nombre"], ", ".join(c["actores"]), ENC[c["id"]], c["avance"] / 100,
            c["obs"] or "Implementado y probado en el ambiente de desarrollo.", PROB.get(c["id"], "Sin problemas abiertos.")]
    for j, v in enumerate(vals):
        cell = ws.cell(row=row, column=j + 1, value=v)
        s = r1.cell(row=8, column=j + 1)
        cell.font, cell.border = copy(s.font), copy(s.border)
        cell.alignment = openpyxl.styles.Alignment(wrap_text=True, vertical="center", horizontal="center" if j in (0, 1, 5) else "left")
    ws.cell(row=row, column=1).number_format = "dd/mm/yyyy"
    ws.cell(row=row, column=6).number_format = "0%"
tot = 6 + len(CU)
ws.cell(row=tot, column=5, value="Avance promedio").font = openpyxl.styles.Font(bold=True)
ws.cell(row=tot, column=6, value=f"=AVERAGE(F6:F{tot-1})").number_format = "0%"
ws.cell(row=tot, column=6).font = openpyxl.styles.Font(bold=True)
ws.cell(row=tot + 2, column=1, value="Nota: la pestaña “Avance 22-09” es el registro anterior. Los casos de uso se rediseñaron cuando el proyecto pasó de alertas a tickets de reposición; la equivalencia está en el documento “Listado de CU, RF y RNF”.")
ws.cell(row=tot + 2, column=1).font = openpyxl.styles.Font(italic=True, size=9)
for extra in ["RESUMEN 3", "RESUMEN 4"]:
    del wb[extra]
wb.move_sheet(ws, offset=-1)
wb.active = 0
wb.save(DST)
print("ok", tot)
