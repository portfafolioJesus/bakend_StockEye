const fs = require("fs");
const path = require("path");
const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell, ImageRun, Header, Footer,
  AlignmentType, WidthType, ShadingType, BorderStyle, HeadingLevel, PageNumber, LevelFormat,
  PageBreak, TableOfContents, VerticalAlign,
} = require("docx");

const AQUI = __dirname;
const D = JSON.parse(fs.readFileSync(path.join(AQUI, "datos.json"), "utf8"));
const OUT = process.argv[2] || path.join(AQUI, "out");
fs.mkdirSync(OUT, { recursive: true });

const FONT = "Calibri";
const AZUL = "1F3A68";
const ANCHO = 9360; // carta con margen de 1"
const EQUIPO = "Jesús González · Ignacio Ruz · Claudio Galiano";

const styles = {
  default: { document: { run: { font: FONT, size: 22 } } },
  paragraphStyles: [
    { id: "Title", name: "Title", basedOn: "Normal", run: { font: FONT, size: 44, bold: true, color: AZUL }, paragraph: { spacing: { before: 0, after: 120 }, keepNext: true } },
    { id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true, run: { font: FONT, size: 32, bold: true, color: AZUL }, paragraph: { spacing: { before: 360, after: 160 }, keepNext: true, outlineLevel: 0 } },
    { id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", quickFormat: true, run: { font: FONT, size: 26, bold: true, color: AZUL }, paragraph: { spacing: { before: 240, after: 120 }, keepNext: true, outlineLevel: 1 } },
  ],
};
const numbering = {
  config: [
    { reference: "vinetas", levels: [{ level: 0, format: LevelFormat.BULLET, text: "•", alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 540, hanging: 270 } } } }] },
  ],
};

const p = (text, opts = {}) => new Paragraph({ spacing: { after: 120, line: 276 }, ...opts, children: Array.isArray(text) ? text : [new TextRun(text)] });
const h1 = (t) => new Paragraph({ heading: HeadingLevel.HEADING_1, children: [new TextRun(t)] });
const h2 = (t) => new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun(t)] });
const bullet = (t) => new Paragraph({ numbering: { reference: "vinetas", level: 0 }, spacing: { after: 60 }, children: Array.isArray(t) ? t : [new TextRun(t)] });
const salto = () => new Paragraph({ children: [new PageBreak()] });

const borde = { style: BorderStyle.SINGLE, size: 4, color: "B8C2D1" };
const bordes = { top: borde, bottom: borde, left: borde, right: borde };

function celda(texto, ancho, { head = false, fill, bold = false, align } = {}) {
  const lineas = Array.isArray(texto) ? texto : [texto];
  return new TableCell({
    width: { size: ancho, type: WidthType.DXA },
    borders: bordes,
    verticalAlign: VerticalAlign.CENTER,
    shading: head ? { fill: AZUL, type: ShadingType.CLEAR, color: "auto" } : fill ? { fill, type: ShadingType.CLEAR, color: "auto" } : undefined,
    margins: { top: 60, bottom: 60, left: 100, right: 100 },
    children: lineas.map((l) => (l instanceof Paragraph ? l : new Paragraph({ alignment: align, spacing: { after: 20 }, children: [new TextRun({ text: String(l), bold: head || bold, color: head ? "FFFFFF" : undefined, size: head ? 20 : 20 })] }))),
  });
}

function tabla(cols, filas, anchos) {
  return new Table({
    width: { size: ANCHO, type: WidthType.DXA },
    columnWidths: anchos,
    rows: [
      new TableRow({ tableHeader: true, children: cols.map((c, i) => celda(c, anchos[i], { head: true })) }),
      ...filas.map((f, j) => new TableRow({ cantSplit: true, children: f.map((v, i) => celda(v, anchos[i], { fill: j % 2 ? "F3F6FA" : undefined, bold: i === 0 })) })),
    ],
  });
}

function imagen(archivo, maxAncho = 624, maxAlto = 660) {
  const buf = fs.readFileSync(archivo);
  const w = buf.readUInt32BE(16), h = buf.readUInt32BE(20); // PNG IHDR
  let ancho = maxAncho, alto = Math.round((h * maxAncho) / w);
  if (alto > maxAlto) { alto = maxAlto; ancho = Math.round((w * maxAlto) / h); }
  return new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 120, after: 80 }, children: [new ImageRun({ type: "png", data: buf, transformation: { width: ancho, height: alto } })] });
}
const leyenda = (t) => new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 240 }, children: [new TextRun({ text: t, italics: true, size: 18, color: "555555" })] });

function portada(titulo, subtitulo) {
  return [
    new Paragraph({ spacing: { before: 2400 }, children: [] }),
    new Paragraph({ style: "Title", children: [new TextRun("StockEye")] }),
    new Paragraph({ spacing: { after: 120 }, children: [new TextRun({ text: titulo, size: 34, color: "333333" })] }),
    new Paragraph({ border: { bottom: { style: BorderStyle.SINGLE, size: 12, color: AZUL, space: 6 } }, spacing: { after: 360 }, children: [new TextRun({ text: subtitulo, size: 22, color: "555555" })] }),
    p("Detección de quiebres de stock en góndolas con visión por computador"),
    p("Proyecto APT · Fase 2 · Entrega final · Noviembre 2026"),
    p("Cliente: Walmart Chile"),
    p(`Equipo: ${EQUIPO}`),
    p("Duoc UC – Escuela de Informática y Telecomunicaciones"),
    salto(),
  ];
}

function documento(nombre, titulo, subtitulo, cuerpo) {
  const doc = new Document({
    creator: "Equipo StockEye", title: `StockEye – ${titulo}`, styles, numbering,
    sections: [{
      properties: { page: { size: { width: 12240, height: 15840 }, margin: { top: 1440, bottom: 1440, left: 1440, right: 1440 } } },
      headers: { default: new Header({ children: [new Paragraph({ alignment: AlignmentType.RIGHT, children: [new TextRun({ text: `StockEye · ${titulo}`, size: 16, color: "888888" })] })] }) },
      footers: { default: new Footer({ children: [new Paragraph({ alignment: AlignmentType.CENTER, children: [new TextRun({ children: ["Página ", PageNumber.CURRENT, " de ", PageNumber.TOTAL_PAGES], size: 16, color: "888888" })] })] }) },
      children: [...portada(titulo, subtitulo), ...cuerpo],
    }],
  });
  return Packer.toBuffer(doc).then((b) => { fs.writeFileSync(path.join(OUT, nombre), b); console.log("escrito", nombre); });
}

const IMG = path.join(AQUI, "img");
const CU = D.CU;
const actoresDe = (c) => c.actores.join(", ");

// ---------- 1. Listado de CU y de RF/RNF ----------
const listado = [
  h1("1. Introducción"),
  p("Este documento reúne los requisitos funcionales (RF), los requisitos no funcionales (RNF) y el listado de casos de uso (CU) de StockEye en su versión final de la Fase 2."),
  p("Respecto a la Fase 1, el proyecto creció: ya no es solo un modelo que detecta espacios vacíos, sino un sistema completo que recibe fotos de cámaras y de celulares, calcula el porcentaje de vacío, abre tickets de reposición, los asigna a reponedores y verifica el cierre con una foto. Por eso los requisitos se reescribieron. En la sección 4 se muestra qué pasó con cada requisito de la Fase 1."),
  h2("1.1 Componentes del sistema"),
  bullet([new TextRun({ text: "API (FastAPI): ", bold: true }), new TextRun("recibe fotos, maneja usuarios, tickets, reportes y administración.")]),
  bullet([new TextRun({ text: "Worker de inferencia: ", bold: true }), new TextRun("analiza cada foto con el modelo SegFormer exportado a ONNX y calcula el % de vacío.")]),
  bullet([new TextRun({ text: "Base de datos (PostgreSQL 16): ", bold: true }), new TextRun("guarda todo y aplica las reglas del ticket (apertura, prioridad, historial).")]),
  bullet([new TextRun({ text: "Notificador y servicio de IA: ", bold: true }), new TextRun("envían push (Firebase / Web Push) y sugieren el producto faltante.")]),
  bullet([new TextRun({ text: "Panel web (React): ", bold: true }), new TextRun("para supervisores y administradores.")]),
  bullet([new TextRun({ text: "App Android (Kotlin): ", bold: true }), new TextRun("para reponedores.")]),
  bullet([new TextRun({ text: "Capturador: ", bold: true }), new TextRun("toma fotos de las cámaras IP del recinto y las sube a la API.")]),
  h2("1.2 Actores"),
  tabla(["Actor", "Descripción", "Dónde trabaja"], [
    ["Reponedor", "Persona de sala que repone productos. Recibe tickets, los atiende y los cierra con una foto.", "App Android"],
    ["Supervisor", "Jefe de turno del recinto. Revisa la bandeja, asigna tickets y mira los reportes.", "Panel web"],
    ["Administrador", "Configura recintos, góndolas, cámaras, usuarios, versiones del modelo e integración de IA.", "Panel web"],
    ["Sistema", "Componentes automáticos: capturador, worker, base de datos, notificador y servicio de IA.", "Servidor / recinto"],
  ], [1800, 5400, 2160]),
  salto(),
  h1("2. Requisitos funcionales"),
  tabla(["ID", "Nombre", "Descripción"], D.RF.map((r) => [r[0], r[1], r[2]]), [1000, 2300, 6060]),
  salto(),
  h1("3. Requisitos no funcionales"),
  tabla(["ID", "Atributo", "Descripción"], D.RNF.map((r) => [r[0], r[1], r[2]]), [1000, 2300, 6060]),
  salto(),
  h1("4. Trazabilidad con la Fase 1"),
  p("Cómo quedó cada requisito definido en la Fase 1 (documento “Presentación idea de Proyecto”)."),
  tabla(["Req. Fase 1", "Nombre", "Qué pasó", "Req. actual", "Comentario"], D.TRAZA.map((t) => [t[0], t[1], t[2], t[3], t[4] || "-"]), [1100, 2100, 1250, 1350, 3560]),
  salto(),
  h1("5. Listado de casos de uso"),
  p("Los casos de uso se agrupan por actor: G (generales), R (reponedor), S (supervisor), A (administrador) y M (máquina o sistema). El detalle de cada uno está en el documento “Planillas de CU”."),
  tabla(["ID", "Caso de uso", "Actor(es)", "RF", "Prioridad"], CU.map((c) => [c.id, c.nombre, actoresDe(c), c.rf.join(", "), c.prioridad]), [1050, 3100, 2350, 1660, 1200]),
  h2("5.1 Matriz RF × CU"),
  p("Qué casos de uso cubren cada requisito funcional."),
  tabla(["RF", "Nombre", "Casos de uso"], D.RF.map((r) => [r[0], r[1], CU.filter((c) => c.rf.includes(r[0])).map((c) => c.id).join(", ") || "Cubierto por el capturador e importación (sin CU propio)"]), [1000, 3400, 4960]),
];

// ---------- 2. Diagramas de CU ----------
const diag = [
  h1("1. Diagrama de casos de uso nivel 0"),
  p("Vista general: los actores y los grandes grupos de funciones del sistema. Firebase y el proveedor de IA (Groq) son sistemas externos."),
  imagen(path.join(IMG, "cu_nivel0.png")),
  leyenda("Figura 1. Diagrama de casos de uso nivel 0."),
  tabla(["Paquete", "Casos de uso que incluye"], [
    ["Acceso", "CU-G01, CU-G02"],
    ["Gestión de tickets", "CU-R01, CU-R03, CU-R04, CU-R05, CU-S01, CU-S02, CU-S03"],
    ["Captura y análisis de imágenes", "CU-R02, CU-S05, CU-M01, CU-M02, CU-M03"],
    ["Reportes y equipo", "CU-S04"],
    ["Administración", "CU-A01 a CU-A06"],
    ["Notificaciones e IA", "CU-G03, CU-M04"],
  ], [3200, 6160]),
  salto(),
  h1("2. Diagramas por actor"),
  h2("2.1 Reponedor"),
  imagen(path.join(IMG, "cu_reponedor.png")),
  leyenda("Figura 2. Casos de uso del reponedor. Tomar foto y cerrar ticket incluyen el análisis de la imagen (CU-M02)."),
  salto(),
  h2("2.2 Supervisor"),
  imagen(path.join(IMG, "cu_supervisor.png")),
  leyenda("Figura 3. Casos de uso del supervisor."),
  salto(),
  h2("2.3 Administrador"),
  imagen(path.join(IMG, "cu_administrador.png")),
  leyenda("Figura 4. Casos de uso del administrador."),
  salto(),
  h2("2.4 Actores de sistema"),
  imagen(path.join(IMG, "cu_sistema.png")),
  leyenda("Figura 5. Casos de uso automáticos. La identificación del producto (CU-M04) solo ocurre si la integración de IA está activa."),
];

// ---------- 3. Planillas de CU ----------
function planilla(c) {
  const fila = (k, v) => new TableRow({ cantSplit: false, children: [celda(k, 2300, { fill: "E8EEF7", bold: true }), celda(v, 7060)] });
  const lista = (arr, num = true) => arr.map((x, i) => new Paragraph({ spacing: { after: 30 }, children: [new TextRun({ text: num ? `${i + 1}. ${x}` : `• ${x}`, size: 20 })] }));
  return [
    h2(`${c.id} ${c.nombre}`),
    new Table({
      width: { size: ANCHO, type: WidthType.DXA }, columnWidths: [2300, 7060],
      rows: [
        fila("ID", c.id),
        fila("Nombre", c.nombre),
        fila("Actor(es)", actoresDe(c)),
        fila("Descripción", c.desc),
        fila("Requisitos asociados", c.rf.join(", ")),
        fila("Prioridad", c.prioridad),
        fila("Precondiciones", lista(c.pre, false)),
        fila("Flujo normal", lista(c.flujo)),
        fila("Flujos alternativos", lista(c.alt, false)),
        fila("Postcondiciones", lista(c.post, false)),
        fila("Estado", `${c.avance}% implementado${c.obs ? ". " + c.obs : ""}`),
      ],
    }),
    new Paragraph({ spacing: { after: 240 }, children: [] }),
  ];
}
const planillas = [
  h1("Especificación de casos de uso"),
  p("Cada planilla describe un caso de uso: quién participa, qué tiene que pasar antes, el paso a paso normal, las alternativas y cómo queda el sistema al final. Los flujos alternativos se numeran según el paso del flujo normal donde ocurren (por ejemplo, 3a ocurre en el paso 3)."),
  ...CU.flatMap((c, i) => (i === 0 ? planilla(c) : [salto(), ...planilla(c)])),
];

// ---------- 4. Diagramas de actividad ----------
const ACT = [
  ["da1", "Detección automática por cámara y apertura de ticket", "CU-M01, CU-M02, CU-M03, CU-M04, CU-G03", "Flujo principal del sistema: desde que la cámara saca la foto hasta que el supervisor ve el ticket en su bandeja."],
  ["da2", "Foto desde la app y creación de ticket", "CU-R02, CU-M02", "El reponedor detecta un quiebre en sala, saca la foto y crea el ticket desde el celular."],
  ["da3", "Asignación e inicio de atención", "CU-S02, CU-G03, CU-R03", "El supervisor asigna el ticket y el reponedor empieza a trabajar."],
  ["da4", "Cierre con foto de verificación", "CU-R04, CU-M02", "El reponedor demuestra con una foto que la góndola quedó repuesta."],
  ["da5", "Inicio de sesión", "CU-G01", "Validación de credenciales y pantalla de inicio según el rol."],
  ["da6", "Publicación de una nueva versión del modelo", "CU-A01", "El administrador sube un modelo nuevo y puede volver atrás si sale peor."],
];
const actividad = [
  h1("Diagramas de actividad"),
  p("Los diagramas muestran los flujos más importantes del sistema. El color de cada acción indica quién la realiza:"),
  tabla(["Color", "Quién"], [
    [new Paragraph({ children: [new TextRun({ text: "■ Verde", color: "2E7D32", bold: true })] }), "Reponedor (app móvil)"],
    [new Paragraph({ children: [new TextRun({ text: "■ Azul", color: "1565C0", bold: true })] }), "Supervisor (panel web)"],
    [new Paragraph({ children: [new TextRun({ text: "■ Naranjo", color: "EF6C00", bold: true })] }), "Administrador (panel web)"],
    [new Paragraph({ children: [new TextRun({ text: "■ Morado", color: "6A1B9A", bold: true })] }), "Sistema (capturador, API, worker, base de datos, notificador, IA)"],
  ], [2400, 6960]),
  p("Los rombos son decisiones, el círculo negro es el inicio y el círculo doble es el fin."),
  ...ACT.flatMap(([f, t, cus, d], i) => [
    salto(),
    h2(`${i + 1}. ${t}`),
    p([new TextRun({ text: "Casos de uso: ", bold: true }), new TextRun(cus)]),
    p(d),
    imagen(path.join(IMG, f + ".png"), 620, 700),
    leyenda(`Figura ${i + 1}. ${t}.`),
  ]),
];

Promise.all([
  documento("StockEye_Listado_CU_RF_RNF.docx", "Listado de CU, RF y RNF", "Requisitos funcionales, no funcionales y casos de uso", listado),
  documento("StockEye_Diagramas_CU.docx", "Diagramas de casos de uso", "Nivel 0 y diagramas por actor", diag),
  documento("StockEye_Planillas_CU.docx", "Planillas de casos de uso", `Especificación de los ${CU.length} casos de uso`, planillas),
  documento("StockEye_Diagramas_Actividad.docx", "Diagramas de actividad", "Flujos principales del sistema", actividad),
]).catch((e) => { console.error(e); process.exit(1); });
