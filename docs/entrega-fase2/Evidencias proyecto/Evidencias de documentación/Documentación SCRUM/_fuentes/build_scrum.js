const fs = require("fs");
const path = require("path");
const { Paragraph, TextRun } = require("docx");
const { p, h1, h2, bullet, salto, tabla, imagen, leyenda, documento } = require("./lib.js");

const S = JSON.parse(fs.readFileSync(path.join(__dirname, "scrum.json"), "utf8"));
const IMG = path.join(__dirname, "img");
const HU = S.HU.map((h) => ({ id: h[0], ep: h[1], rol: h[2], quiero: h[3], para: h[4], crit: h[5], pts: h[6], mos: h[7], valor: h[8], cu: h[9], jira: h[10], estado: h[11], sprint: S.SP[h[0]] }));
const EP = Object.fromEntries(S.EPICAS.map((e) => [e[0], e[1]]));
const historia = (h) => `Como ${h.rol}, quiero ${h.quiero}, para ${h.para}.`;
const b = (t) => new TextRun({ text: t, bold: true });
const t = (x) => new TextRun(x);

// ---------- Análisis del caso ----------
const analisis = [
  h1("1. Contexto"),
  p("Walmart Chile pierde ventas cuando un producto se acaba en la góndola y nadie lo nota a tiempo (quiebre de stock). Hoy la revisión es manual: un reponedor o supervisor recorre los pasillos y detecta el vacío a simple vista. En una tienda grande eso significa que un quiebre puede pasar horas sin reponerse."),
  p("Las tiendas ya tienen cámaras de seguridad que ven las góndolas, pero sus imágenes no se usan para esto. Además son difíciles de analizar: ángulos tipo ojo de pez, reflejos en estantes metálicos, vapor en refrigeradores y zonas ciegas aparecen en cerca del 90 % de las fotos."),
  h1("2. Problema"),
  p("No existe una forma automática y confiable de saber qué góndolas tienen espacios vacíos, cuánto vacío hay y quién debe reponer, ni de comprobar que la reposición se hizo."),
  h1("3. Interesados (stakeholders)"),
  tabla(["Interesado", "Qué necesita"], [
    ["Walmart Chile (cliente)", "Reducir quiebres de stock con una solución reproducible que corra en su infraestructura y con sus cámaras."],
    ["Supervisor de sala", "Ver de un vistazo qué góndolas están vacías, priorizar y repartir el trabajo entre reponedores."],
    ["Reponedor", "Saber qué reponer y dónde, desde el celular, con pocos toques."],
    ["Administrador / TI de Walmart", "Instalar, configurar cámaras y usuarios, y actualizar el modelo sin depender del equipo."],
    ["Duoc UC (docentes y comisión)", "Un proyecto documentado según la metodología y la estructura de entrega."],
  ], [3000, 6360]),
  h1("4. Solución propuesta: StockEye"),
  p("StockEye toma fotos de las góndolas (desde cámaras IP o desde el celular del reponedor), calcula el porcentaje de vacío con un modelo de segmentación (SegFormer exportado a ONNX, menos de 3 s por foto en CPU) y, si supera el umbral del recinto, abre un ticket de reposición con prioridad automática. El supervisor lo asigna desde un panel web y el reponedor lo cierra en la app Android con una foto que verifica la reposición."),
  h2("Cambio de alcance respecto a la Fase 1"),
  p("En la Fase 1 el foco era el modelo de visión y una alerta con semáforo. Durante la Fase 2, al validar con el cliente, se vio que una alerta sola no asegura que alguien reponga. Por eso la alerta evolucionó a un ticket con responsable, estados, historial y cierre verificado, y se agregó la captura automática desde cámaras. También se cambió la detección por cajas (YOLO) por segmentación (SegFormer), que entrega un % de vacío más preciso."),
  h1("5. Alcance"),
  tabla(["Incluye", "No incluye"], [
    ["Detección de % de vacío por góndola", "Clasificar cada producto individualmente"],
    ["Tickets con prioridad, asignación y cierre verificado", "Integración con el sistema de inventario de Walmart"],
    ["App Android para reponedores", "App para iOS"],
    ["Panel web para supervisores y administradores", "Análisis de video en tiempo real (se usan fotos fijas)"],
    ["Notificaciones push y sugerencia de producto con IA", "Distinguir vacío real de espacio no apilable (mejora futura)"],
  ], [4680, 4680]),
  h1("6. Restricciones"),
  bullet("Entrenamiento con un máximo de 4 GB de VRAM (Google Colab / Kaggle)."),
  bullet("Inferencia en CPU, entre 2 y 5 s por imagen según Walmart; el equipo se fijó como meta 3 s."),
  bullet("Instalación reproducible siguiendo solo un manual (Docker Compose)."),
  bullet("Datasets con licencia que permita uso académico y comercial."),
  bullet("Plazo: un semestre (agosto a noviembre de 2026), equipo de 3 personas."),
  h1("7. Riesgos"),
  tabla(["Riesgo", "Impacto", "Cómo se mitiga"], [
    ["Pocas imágenes reales de Walmart", "Alto", "Dataset propio con fotos en terreno + datasets públicos + aumento de datos."],
    ["Modelo no cumple el tiempo de 3 s", "Alto", "Exportación a ONNX y ajuste de resolución; medición p95."],
    ["Condiciones visuales difíciles (reflejos, ojo de pez)", "Medio", "Entrenar con fotos de las cámaras reales; umbral configurable por recinto."],
    ["Dependencia de servicios externos (Firebase, IA)", "Medio", "Son opcionales: si fallan, la detección y los tickets siguen funcionando."],
    ["Cambios de alcance tarde en el semestre", "Medio", "Backlog priorizado (MoSCoW) y sprints cortos de 2 semanas."],
  ], [3200, 1200, 4960]),
  h1("8. Equipo y roles Scrum"),
  tabla(["Rol Scrum", "Quién", "Responsabilidad"], [
    ["Product Owner", "Contraparte de Walmart Chile", "Define qué aporta valor y valida los avances."],
    ["Scrum Master", "Claudio Galiano", "Mantiene el tablero en Jira y la Carta Gantt, coordina reuniones y la documentación."],
    ["Equipo de desarrollo", "Jesús González", "Backend, base de datos, panel web, despliegue."],
    ["Equipo de desarrollo", "Ignacio Ruz", "Datos, entrenamiento y evaluación del modelo de visión."],
    ["Equipo de desarrollo", "Claudio Galiano", "App Android, prototipos de interfaz (UI/UX)."],
  ], [2000, 3000, 4360]),
  h1("9. Metodología"),
  p("El equipo combinó Scrum con CRISP-DM. Las etapas de CRISP-DM (comprensión del negocio y de los datos, preparación, modelado y evaluación) ordenan el trabajo del modelo de visión, y Scrum ordena el producto en sprints de 2 semanas con un backlog priorizado. El tablero se lleva en Jira (espacio StockEye, clave SKT) y el calendario en la Carta Gantt."),
  p("El detalle de épicas, sprints e historias está en el documento “Épicas, Sprints y Historias de Usuario”, y su priorización en “Priorización de H.U.”."),
];

// ---------- Épicas, sprints e HU ----------
const ptsEp = (e) => HU.filter((h) => h.ep === e).reduce((a, h) => a + h.pts, 0);
const ptsSp = (s) => HU.filter((h) => h.sprint === s).reduce((a, h) => a + h.pts, 0);
const epicas = [
  h1("1. Cómo se organizó el trabajo"),
  p("El backlog del producto se ordenó en épicas (grandes objetivos), historias de usuario (lo que necesita cada rol) y sprints de 2 semanas. Las historias se estimaron en puntos de historia con la serie de Fibonacci (1, 2, 3, 5, 8) y se enlazan con las tareas del tablero de Jira (claves SKT-n) y con los casos de uso (CU)."),
  p("Las tareas de Jira se crearon a partir de la Carta Gantt; las historias de este documento agrupan esas tareas desde el punto de vista del usuario."),
  h1("2. Épicas"),
  tabla(["ID", "Épica", "Objetivo", "Épica en Jira", "Responsable", "Puntos"], S.EPICAS.map((e) => [e[0], e[1], e[2], e[3], e[4], String(ptsEp(e[0]))]), [800, 1700, 2900, 1500, 1660, 800]),
  salto(),
  h1("3. Sprints"),
  tabla(["Sprint", "Período", "Objetivo del sprint", "Historias", "Puntos"], S.SPRINTS.map((s) => [s[0], s[1], s[2], s[3].join(", "), String(ptsSp(s[0]))]), [1000, 1500, 3700, 2260, 900]),
  imagen(path.join(IMG, "scrum_velocidad.png"), 624),
  leyenda("Figura 1. Puntos completados por sprint y burndown del backlog (156 puntos en total)."),
  p("La velocidad sube desde el Sprint 4, cuando el modelo ya estaba listo y el equipo pasó a construir el sistema. Los sprints 0 a 3 tienen menos puntos porque estuvieron dedicados al análisis y a los datos, que según CRISP-DM son la base del modelo."),
  h2("Ceremonias"),
  bullet([b("Planificación del sprint: "), t("al inicio de cada sprint se eligen las historias del backlog priorizado y se dividen en tareas en Jira.")]),
  bullet([b("Reunión de seguimiento: "), t("el equipo revisa el tablero varias veces por semana (qué hice, qué haré, qué me bloquea).")]),
  bullet([b("Revisión: "), t("al cierre se muestra lo construido al docente y, cuando corresponde, al cliente.")]),
  bullet([b("Retrospectiva: "), t("se registra qué funcionó y qué mejorar en los diarios de reflexión de cada integrante.")]),
  salto(),
  h1("4. Historias de usuario"),
  ...S.EPICAS.flatMap((e) => {
    const hs = HU.filter((h) => h.ep === e[0]);
    return [
      h2(`${e[0]} ${e[1]}`),
      tabla(["ID", "Historia", "Criterios de aceptación", "Pts", "Sprint", "Estado"],
        hs.map((h) => [h.id, historia(h), h.crit.map((c) => "• " + c), String(h.pts), h.sprint.replace("Sprint ", "S"), h.estado]),
        [750, 3000, 3110, 500, 650, 1350]),
      new Paragraph({ spacing: { after: 160 }, children: [] }),
    ];
  }),
  salto(),
  h1("5. Trazabilidad"),
  tabla(["Historia", "Casos de uso", "Tareas en Jira"], HU.map((h) => [h.id, h.cu, h.jira]), [1400, 3000, 4960]),
];

// ---------- Priorización ----------
const orden = [...HU].sort((a, c) => ({ Must: 0, Should: 1, Could: 2 }[a.mos] - { Must: 0, Should: 1, Could: 2 }[c.mos]) || (c.valor / c.pts - a.valor / a.pts));
const cuenta = (m) => HU.filter((h) => h.mos === m).length;
const priorizacion = [
  h1("1. Método"),
  p("Las historias se priorizaron en dos pasos:"),
  bullet([b("MoSCoW: "), t("cada historia se clasificó como Must (imprescindible para que el sistema sirva), Should (importante, pero el sistema funciona sin ella), Could (deseable si hay tiempo) o Won't (fuera de este semestre).")]),
  bullet([b("Valor / esfuerzo: "), t("dentro de cada grupo se ordenó por valor para el negocio (1 a 5, acordado con el cliente) dividido por el esfuerzo en puntos de historia. Primero lo que aporta más valor con menos trabajo.")]),
  p("Además se respetaron las dependencias: sin datos no hay modelo, sin modelo no hay tickets automáticos, y sin login no hay app ni panel."),
  h1("2. Resultado MoSCoW"),
  tabla(["Categoría", "Historias", "Qué significa en StockEye"], [
    ["Must", String(cuenta("Must")), "Detectar el vacío, abrir el ticket, asignarlo, atenderlo y cerrarlo con foto. Es el núcleo del producto."],
    ["Should", String(cuenta("Should")), "Notificaciones push, reportes, comentarios, edición de tickets y prototipos."],
    ["Could", String(cuenta("Could")), "Sugerencia del producto faltante con IA."],
    ["Won't (este semestre)", "—", "Distinguir vacío real de espacio no apilable, app iOS, integración con inventario."],
  ], [2000, 1200, 6160]),
  salto(),
  h1("3. Backlog priorizado"),
  tabla(["#", "ID", "Historia (resumen)", "MoSCoW", "Valor", "Pts", "Valor/Pts", "Sprint"],
    orden.map((h, i) => [String(i + 1), h.id, `${h.rol[0].toUpperCase() + h.rol.slice(1)}: ${h.quiero}`, h.mos, String(h.valor), String(h.pts), (h.valor / h.pts).toFixed(2), h.sprint.replace("Sprint ", "S")]),
    [450, 800, 3810, 950, 750, 600, 1000, 1000]),
  h1("4. Comentarios"),
  bullet("Las historias de datos y modelo (EP-01) son Must y se hicieron primero aunque tienen valor/esfuerzo bajo, porque todo lo demás depende de ellas."),
  bullet("La sugerencia de producto con IA quedó como Could: aporta, pero el sistema cumple su objetivo sin ella. Por eso es opcional y se puede apagar."),
  bullet("Las notificaciones push quedaron como Should: el panel ya se actualiza en tiempo real, pero el reponedor necesita el aviso en el celular."),
];

Promise.all([
  documento("StockEye_Analisis_del_Caso.docx", "Análisis del caso", "Documentación SCRUM", analisis),
  documento("StockEye_Epicas_Sprints_HU.docx", "Épicas, Sprints y Historias de Usuario", "Documentación SCRUM", epicas),
  documento("StockEye_Priorizacion_HU.docx", "Priorización de Historias de Usuario", "Documentación SCRUM", priorizacion),
]).catch((e) => { console.error(e); process.exit(1); });
