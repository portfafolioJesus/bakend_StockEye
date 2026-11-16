// Anexo SCRUM resumido: lo esencial de análisis, backlog, sprints, priorización y Jira.
const fs = require("fs");
const path = require("path");
const { Paragraph, TextRun } = require("docx");
const { p, h1, h2, bullet, salto, tabla, imagen, leyenda, documento } = require("./lib.js");
const { HU, S } = require("./build_scrum.js");
const J = JSON.parse(fs.readFileSync(path.join(__dirname, "jira.json"), "utf8"));
const b = (t) => new TextRun({ text: t, bold: true });
const t = (x) => new TextRun(x);

// Estado de Jira tras la actualización del 15-11-2026
const LISTO = ["SKT-12", "SKT-14", "SKT-21", "SKT-41", "SKT-42", "SKT-49", "SKT-50", "SKT-51", "SKT-52", "SKT-53", "SKT-54", "SKT-55", "SKT-56", "SKT-58", "SKT-60", "SKT-61", "SKT-62", "SKT-63", "SKT-65", "SKT-66", "SKT-67", "SKT-69", "SKT-70"];
const CURSO = ["SKT-68", "SKT-71", "SKT-72", "SKT-73", "SKT-74"];
const estado = (x) => (LISTO.includes(x.key) ? "Listo" : CURSO.includes(x.key) ? "En curso" : x.estado);
const epJ = [...new Set(J.map((x) => x.epica))];
const cnt = (arr, e) => arr.filter((x) => estado(x) === e).length;
const pts = (s) => HU.filter((h) => h.sprint === s).reduce((a, h) => a + h.pts, 0);

const cuerpo = [
  h1("1. El caso"),
  p("Walmart Chile pierde ventas cuando un producto se acaba en la góndola y nadie lo nota a tiempo. StockEye analiza fotos de las góndolas (cámaras de sala o celular del reponedor), calcula el % de vacío con un modelo de segmentación y, si supera el umbral del recinto, abre un ticket de reposición con prioridad automática. El supervisor lo asigna desde un panel web y el reponedor lo cierra en la app con una foto que verifica la reposición."),
  h2("Roles Scrum"),
  tabla(["Rol", "Quién"], [
    ["Product Owner", "José Larraín – Walmart Chile, área de Inteligencia Artificial"],
    ["Docente guía / Jefe de proyecto", "Arturo Vargas – Duoc UC"],
    ["Scrum Master", "Claudio Galiano"],
    ["Equipo de desarrollo", "Jesús González (backend, BD, panel web) · Ignacio Ruz (datos y modelo) · Claudio Galiano (app móvil, UI/UX)"],
  ], [3000, 6360]),
  h2("Metodología"),
  p("En la Fase 1 el equipo definió un enfoque Kanban + CRISP-DM: CRISP-DM para el modelo de visión y seguimiento de actividades con la Carta Gantt. Para esta entrega, el trabajo real del semestre se ordenó en formato Scrum: épicas, historias de usuario y sprints de 2 semanas (el mismo largo del ciclo de evaluación de Walmart)."),
  p([b("Nota: "), t("los sprints de este anexo son una reconstrucción hecha al cierre del proyecto a partir de la Carta Gantt y del repositorio. Agrupan en períodos de 2 semanas el trabajo que efectivamente se realizó; no corresponden a sprints creados en una herramienta durante el semestre.")]),
  h2("Riesgos principales (Matriz de Riesgo Fase 1)"),
  tabla(["Riesgo", "Mitigación", "Estado"], [
    ["Dataset insuficiente o poco representativo", "Fotos propias en terreno + datasets con licencia + aumento de datos", "Mitigado"],
    ["El modelo no generaliza a sala real", "Entrenar con fotos reales; umbral configurable por recinto", "En seguimiento"],
    ["Inferencia sobre 2–5 s", "ONNX en CPU: 1,1–2,0 s por foto", "Cerrado"],
    ["Retraso en la retroalimentación de Walmart", "Holguras en la Carta Gantt entre cada ciclo", "Mitigado"],
    ["Documentación insuficiente para instalar", "Manual + Docker Compose + script único de BD", "Cerrado"],
  ], [3300, 4560, 1500]),

  h1("2. Product Backlog"),
  h2("Épicas"),
  tabla(["ID", "Épica", "Historias", "Puntos"], S.EPICAS.map((e) => [e[0], e[1], String(HU.filter((h) => h.ep === e[0]).length), String(HU.filter((h) => h.ep === e[0]).reduce((a, h) => a + h.pts, 0))]), [1000, 5360, 1500, 1500]),
  p(`En total ${HU.length} historias y ${HU.reduce((a, h) => a + h.pts, 0)} puntos. Las 16 historias de la Fase 1 (alertas con semáforo) evolucionaron a este backlog de tickets de reposición.`),
  h2("Historias de usuario"),
  tabla(["ID", "Como… quiero…", "Pts", "Prioridad", "Sprint", "Estado"],
    HU.map((h) => [h.id, `${h.rol[0].toUpperCase() + h.rol.slice(1)}: ${h.quiero}`, String(h.pts), h.mos, h.sprint.replace("Sprint ", "S"), h.estado.replace(/ \(.*\)/, "")]),
    [800, 4960, 550, 1050, 800, 1200]),
  p("El detalle de cada historia (para qué, criterios de aceptación, casos de uso y tareas de Jira) está en el documento “Épicas, Sprints y Historias de Usuario”.", { spacing: { before: 120 } }),

  salto(),
  h1("3. Sprints"),
  tabla(["Sprint", "Período", "Objetivo", "Pts"], S.SPRINTS.map((s) => [s[0], s[1], s[2], String(pts(s[0]))]), [1100, 1900, 5560, 800]),
  imagen(path.join(__dirname, "img", "scrum_velocidad.png"), 600),
  leyenda("Figura 1. Puntos por sprint y burndown del backlog."),
  h2("Cómo se coordinó el equipo"),
  bullet([b("Reuniones de equipo: "), t("jueves y viernes. Además, reuniones de 1 a 2 horas los fines de semana, y jornadas largas antes de las entregas (por ejemplo, más de 6 horas el domingo 15-11).")]),
  bullet([b("Consultas con el docente: "), t("los viernes, con Arturo Vargas, para revisar avances y resolver dudas.")]),
  bullet([b("Comunicación diaria: "), t("WhatsApp y Discord, para avisar avances, bloqueos y coordinar tareas.")]),
  bullet([b("Retroalimentación del cliente: "), t("en los hitos de evaluación con Walmart.")]),
  bullet([b("Reflexión: "), t("los aprendizajes y ajustes de cada etapa quedaron en los diarios de reflexión de cada integrante.")]),
  p([b("Criterio de terminado: "), t("una tarea se considera lista cuando cumple sus criterios de aceptación, está en GitHub y, cuando aplica, pasan sus pruebas automáticas.")]),

  h1("4. Priorización"),
  p("MoSCoW (Must, Should, Could, Won't) y, dentro de cada grupo, valor para el negocio dividido por esfuerzo en puntos, respetando dependencias (sin datos no hay modelo, sin modelo no hay tickets)."),
  tabla(["Categoría", "Historias", "Ejemplos"], [
    ["Must", String(HU.filter((h) => h.mos === "Must").length), "Detectar el vacío, ticket automático, asignar, atender y cerrar con foto, login, instalación."],
    ["Should", String(HU.filter((h) => h.mos === "Should").length), "Notificaciones push, reportes, comentarios, edición de tickets, prototipos."],
    ["Could", String(HU.filter((h) => h.mos === "Could").length), "Sugerencia del producto faltante con IA."],
    ["Won't", "—", "Vacío real vs. no apilable, app iOS, integración con inventario."],
  ], [1600, 1300, 6460]),

  h1("5. Tablero en Jira"),
  p(`El tablero en Jira (espacio StockEye, clave SKT) se creó el 10-11-2026 a partir de la Carta Gantt, para ordenar el cierre del proyecto y tener el seguimiento en una herramienta compartida. Tiene 9 épicas, una por fase de la Gantt, y ${J.length} tareas con responsable y área. Hasta esa fecha el seguimiento se llevaba en la Carta Gantt y en las reuniones del equipo.`),
  p("Estado de las tareas al 15-11-2026, actualizado según lo que está terminado en el repositorio:"),
  tabla(["Épica en Jira", "Tareas", "Listo", "En curso", "Por hacer"], [
    ...epJ.map((e) => { const xs = J.filter((x) => x.epica === e); return [e, String(xs.length), String(cnt(xs, "Listo")), String(cnt(xs, "En curso")), String(cnt(xs, "Por hacer"))]; }),
    ["Total", String(J.length), String(cnt(J, "Listo")), String(cnt(J, "En curso")), String(cnt(J, "Por hacer"))],
  ], [4360, 1250, 1250, 1250, 1250]),
  new Paragraph({ spacing: { before: 160, after: 160 }, children: [new TextRun({ text: "Captura del tablero de Jira:", bold: true })] }),
  new Paragraph({ spacing: { after: 160 }, children: [new TextRun({ text: "[Pegar aquí una captura del tablero (vista Tablero) y otra de la lista de tareas.]", italics: true, highlight: "yellow" })] }),
];

documento("StockEye_Anexo_SCRUM.docx", "Anexo: Documentación SCRUM", "Resumen de análisis, backlog, sprints, priorización y tablero Jira", cuerpo).catch((e) => { console.error(e); process.exit(1); });
