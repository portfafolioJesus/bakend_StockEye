const fs = require("fs");
const path = require("path");
const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell, ImageRun, Header, Footer,
  AlignmentType, WidthType, ShadingType, BorderStyle, HeadingLevel, PageNumber, LevelFormat,
  PageBreak, TableOfContents, VerticalAlign, PageOrientation,
} = require("docx");

const AQUI = __dirname;
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

function documento(nombre, titulo, subtitulo, cuerpo, extra = []) {
  const hdr = () => ({ default: new Header({ children: [new Paragraph({ alignment: AlignmentType.RIGHT, children: [new TextRun({ text: `StockEye · ${titulo}`, size: 16, color: "888888" })] })] }) });
  const ftr = () => ({ default: new Footer({ children: [new Paragraph({ alignment: AlignmentType.CENTER, children: [new TextRun({ children: ["Página ", PageNumber.CURRENT, " de ", PageNumber.TOTAL_PAGES], size: 16, color: "888888" })] })] }) });
  const doc = new Document({
    creator: "Equipo StockEye", title: `StockEye – ${titulo}`, styles, numbering,
    sections: [{
      properties: { page: { size: { width: 12240, height: 15840 }, margin: { top: 1440, bottom: 1440, left: 1440, right: 1440 } } },
      headers: { default: new Header({ children: [new Paragraph({ alignment: AlignmentType.RIGHT, children: [new TextRun({ text: `StockEye · ${titulo}`, size: 16, color: "888888" })] })] }) },
      footers: { default: new Footer({ children: [new Paragraph({ alignment: AlignmentType.CENTER, children: [new TextRun({ children: ["Página ", PageNumber.CURRENT, " de ", PageNumber.TOTAL_PAGES], size: 16, color: "888888" })] })] }) },
      children: [...portada(titulo, subtitulo), ...cuerpo],
    }, ...extra.map((e) => ({
      properties: { page: { size: { width: 12240, height: 15840, orientation: e.landscape ? PageOrientation.LANDSCAPE : PageOrientation.PORTRAIT }, margin: { top: 1080, bottom: 1080, left: 1080, right: 1080 } } },
      headers: hdr(), footers: ftr(), children: e.children,
    }))],
  });
  return Packer.toBuffer(doc).then((b) => { fs.writeFileSync(path.join(OUT, nombre), b); console.log("escrito", nombre); });
}

module.exports = { p, h1, h2, bullet, salto, celda, tabla, imagen, leyenda, portada, documento, styles, numbering, ANCHO, AZUL, FONT, EQUIPO, OUT };
