const fs = require("fs");
const path = require("path");
const { Paragraph, TextRun, Table, TableRow, WidthType } = require("docx");
const { p, h1, h2, bullet, salto, tabla, celda, documento } = require("./lib.js");
const T = JSON.parse(fs.readFileSync(path.join(__dirname, "pruebas.json"), "utf8"));
const b = (t) => new TextRun({ text: t, bold: true });
const t = (x) => new TextRun(x);

function tablaAncha(cols, filas, anchos) {
  const total = anchos.reduce((a, x) => a + x, 0);
  return new Table({
    width: { size: total, type: WidthType.DXA }, columnWidths: anchos,
    rows: [
      new TableRow({ tableHeader: true, children: cols.map((c, i) => celda(c, anchos[i], { head: true })) }),
      ...filas.map((f, j) => new TableRow({ cantSplit: true, children: f.map((v, i) => celda(v, anchos[i], { fill: j % 2 ? "F3F6FA" : undefined, bold: i === 0 })) })),
    ],
  });
}

const cuerpo = [
  h1("1. Objetivo"),
  p("Este plan define cómo se prueba StockEye para comprobar que cumple los requisitos funcionales y no funcionales antes de entregarlo a Walmart: qué se prueba, cómo, con qué datos, quién lo hace y cuándo se considera aprobado."),
  h1("2. Alcance"),
  tabla(["Se prueba", "No se prueba en esta fase"], [
    ["API REST, worker de inferencia, notificador, servicio de IA", "Cámaras reales de Walmart (se usa una cámara simulada)"],
    ["Reglas de negocio de la base de datos", "Carga con más de 2 recintos en paralelo en producción"],
    ["App Android (flujo del reponedor)", "Compatibilidad con iOS"],
    ["Panel web (flujos de supervisor y administrador)", "Precisión del modelo contra el dataset oculto de Walmart (lo evalúa el cliente)"],
    ["Rendimiento del análisis (≤ 3 s por foto)", ""],
  ], [4680, 4680]),
  h1("3. Estrategia"),
  tabla(["Nivel", "Qué cubre", "Herramienta", "Responsable"], [
    ["Unitarias e integración", "Backend, cola de análisis, inferencia, permisos", "pytest (backend/tests)", "Jesús González"],
    ["Reglas de base de datos", "Restricciones, triggers y claves foráneas", "psql + db/tests/test_reglas.sql", "Jesús González"],
    ["Rendimiento", "Tiempo de análisis por foto y efecto de ráfagas", "pytest + herramientas/simular_camaras.py", "Ignacio Ruz"],
    ["Funcionales (sistema)", "Cada caso de uso en la app y el panel", "Manual, con los datos de demo", "Claudio Galiano"],
    ["Aceptación / usuario", "Flujos completos de reponedor y supervisor", "Sesión guiada con usuarios", "Todo el equipo"],
  ], [2000, 3100, 2560, 1700]),
  h2("3.1 Ambiente de pruebas"),
  bullet("Docker Compose con la demo cargada (2 recintos, 8 usuarios, 5 tickets) según el Instructivo de instalación."),
  bullet("Base de datos de pruebas stockeye_test (pytest la recrea en cada prueba)."),
  bullet("Emulador de Android Studio (API 24 o superior) o celular Android en la misma red."),
  bullet("Navegador Chrome o Firefox para el panel."),
  h2("3.2 Criterios de aceptación"),
  bullet("100 % de las pruebas automáticas (pytest y reglas de BD) en verde."),
  bullet("Todos los casos funcionales de prioridad Alta aprobados."),
  bullet("Ningún defecto crítico abierto (que impida abrir, asignar o cerrar un ticket)."),
  bullet("p95 del análisis por foto ≤ 3 s en el equipo de referencia."),
  h2("3.3 Cómo correr las pruebas automáticas"),
  p([b("Backend: "), t("cd backend && STOCKEYE_TEST_DATABASE_URL=postgresql://…/stockeye_test .venv/bin/python -m pytest")]),
  p([b("Reglas de BD: "), t("psql -d stockeye_test -f db/tests/test_reglas.sql (sobre una copia con el seed).")]),
  salto(),
  h1("4. Pruebas automáticas del backend"),
  p(`El repositorio tiene ${T.pytest.length} pruebas automáticas en backend/tests. Cubren el flujo principal, la cola concurrente, la inferencia y los permisos.`),
  tabla(["Archivo", "Prueba", "Qué verifica", "CU"], T.pytest.map((x) => [x[0], x[1], x[2], x[3]]), [1350, 3300, 3610, 1100]),
  h1("5. Pruebas de reglas de la base de datos"),
  p("Ejecutadas el 15-11-2026 sobre una base PostgreSQL 16 creada con las migraciones 001–004 y el seed de demo. Las 8 reglas se cumplen."),
  tabla(["#", "Caso", "Esperado", "Resultado obtenido", "Estado"], T.reglas.map((r) => [r[0], r[1], r[2], r[3], "Aprobado"]), [450, 2700, 1700, 3410, 1100]),
  h1("6. Pruebas de rendimiento"),
  p("Medición del equipo en un PC de referencia (Ryzen 5 3400G, 4 núcleos, sin GPU) con el modelo SegFormer en ONNX. Requisito: RNF-01, máximo 3 s por foto."),
  tabla(["Hilos", "Píxeles de entrada", "p50 por foto", "p95", "RAM del worker", "¿Cumple?"], [
    ["2", "740 mil (≈1152×640)", "1,8 s", "1,9 s", "~0,9 GB", "Sí"],
    ["2", "600 mil (≈1024×576)", "1,45 s", "1,5 s", "~0,8 GB", "Sí"],
    ["4", "600 mil", "1,0 s", "1,1 s", "~1,0 GB", "Sí"],
    ["4", "900 mil (≈1280×704)", "1,65 s", "2,0 s", "~1,5 GB", "Sí"],
  ], [900, 2300, 1500, 1200, 1700, 1760]),
  p("Prueba de carga: con simular_camaras.py se envía una ráfaga de 30 fotos desde un recinto y fotos normales desde otros 3; los otros recintos siguen siendo atendidos gracias a los turnos de la cola (prueba test_rafaga_de_un_recinto_no_bloquea_a_otro)."),
  h1("7. Pruebas de aceptación de usuario"),
  tabla(["Flujo", "Usuario", "Qué se observa"], [
    ["Reponedor: foto → ticket → empezar → cerrar con foto", "Reponedor (dsoto)", "Tiempo para completar, toques necesarios, dudas al usar la app."],
    ["Supervisor: bandeja → asignar → seguimiento → reporte", "Supervisora (cmunoz)", "Claridad de la bandeja, facilidad para asignar, utilidad del reporte."],
    ["Administrador: crear cámara → invitar usuario → activar modelo", "Administrador", "Que pueda hacerlo solo, siguiendo la interfaz."],
  ], [3600, 1900, 3860]),
  h1("8. Registro de defectos"),
  p("Cada defecto encontrado se registra en Jira (tipo Error) con este formato:"),
  tabla(["Campo", "Contenido"], [
    ["ID", "SKT-n (lo asigna Jira)"],
    ["Caso de prueba", "CP-xx donde apareció"],
    ["Severidad", "Crítica / Alta / Media / Baja"],
    ["Pasos para reproducir", "Paso a paso con los datos usados"],
    ["Resultado esperado / obtenido", "Qué debía pasar y qué pasó"],
    ["Evidencia", "Captura de pantalla o log"],
    ["Estado", "Abierto → En corrección → Verificado → Cerrado"],
  ], [3000, 6360]),
];

const casos = [{
  landscape: true, children: [
    h1("9. Casos de prueba funcionales"),
    p(`Un caso por flujo normal y por cada flujo alternativo de los casos de uso (${T.casos.length} en total). Las columnas Resultado obtenido y Estado se completan al ejecutar las pruebas sobre la demo.`),
    tablaAncha(["ID", "CU", "Caso", "Precondición", "Pasos", "Datos", "Resultado esperado", "Resultado obtenido", "Estado"],
      T.casos.map((c) => [c.id, c.cu, c.nombre, c.pre, c.pasos.length > 1 ? c.pasos.map((s, i) => `${i + 1}. ${s}`) : c.pasos[0], c.datos, c.esperado, "", ""]),
      [750, 800, 1700, 1500, 3100, 1500, 2130, 1300, 900]),
  ],
}];

documento("StockEye_Plan_de_Pruebas.docx", "Plan de pruebas", "Estrategia, casos de prueba y resultados", cuerpo, casos).catch((e) => { console.error(e); process.exit(1); });
