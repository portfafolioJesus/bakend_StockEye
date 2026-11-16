const fs = require("fs");
const path = require("path");
const { Paragraph, TextRun } = require("docx");
const { p, h1, h2, bullet, salto, tabla, imagen, leyenda, documento } = require("./lib.js");

const S = JSON.parse(fs.readFileSync(path.join(__dirname, "scrum.json"), "utf8"));
const IMG = path.join(__dirname, "img");
const HU = S.HU.map((h) => ({ id: h[0], ep: h[1], rol: h[2], quiero: h[3], para: h[4], crit: h[5], pts: h[6], mos: h[7], valor: h[8], cu: h[9], jira: h[10], estado: h[11], sprint: S.SP[h[0]] }));
const historia = (h) => `Como ${h.rol}, quiero ${h.quiero}, para ${h.para}.`;
const b = (t) => new TextRun({ text: t, bold: true });
const t = (x) => new TextRun(x);

// ================= 1. Análisis del caso =================
const analisis = [
  h1("1. Contexto"),
  p("El caso fue entregado por Walmart Chile a través de su área de Inteligencia Artificial. En el kickoff, José Larraín nos presentó el problema: en las salas de venta los productos se acaban en la góndola y muchas veces nadie se da cuenta a tiempo. Eso es lo que se conoce como quiebre de stock y se traduce directamente en ventas perdidas."),
  p("Actualmente la detección es manual. Un reponedor o el supervisor recorre los pasillos y ve los vacíos a simple vista, lo que en un local grande puede tomar horas. Las tiendas ya cuentan con cámaras de seguridad que apuntan a las góndolas, pero esas imágenes no se aprovechan para esto. Además no son fáciles de procesar: hay ángulos tipo ojo de pez, reflejos en los estantes metálicos, vapor en los refrigeradores y zonas que la cámara no alcanza a ver."),
  h1("2. Problema"),
  p("No existe una forma automática de saber qué góndolas tienen espacios vacíos, cuánto falta, quién tiene que reponer y si la reposición efectivamente se hizo."),
  h1("3. Stakeholders"),
  tabla(["Stakeholder", "Necesidad"], [
    ["Walmart Chile (cliente)", "Reducir los quiebres de stock con una solución que funcione en su infraestructura y con sus cámaras."],
    ["Supervisor de sala", "Ver qué góndolas están vacías, priorizar y repartir el trabajo entre los reponedores."],
    ["Reponedor", "Saber qué reponer y dónde, desde el celular y sin perder tiempo."],
    ["Administrador / TI", "Instalar el sistema, configurar cámaras y usuarios y actualizar el modelo sin depender de nosotros."],
    ["Duoc UC", "Un proyecto documentado según la metodología y la estructura de entrega de la asignatura."],
  ], [3000, 6360]),
  h1("4. Solución propuesta"),
  p("StockEye recibe fotos de las góndolas, ya sea desde las cámaras IP del local o desde el celular del reponedor. Cada foto se analiza con un modelo de segmentación (SegFormer exportado a ONNX) que calcula el porcentaje de vacío en menos de 3 segundos usando solo CPU. Si ese porcentaje supera el umbral configurado para el recinto, el sistema abre un ticket de reposición con prioridad calculada automáticamente."),
  p("El supervisor ve los tickets en un panel web y los asigna a un reponedor. El reponedor los atiende desde una app Android y, para cerrarlos, tiene que tomar una foto nueva que el sistema vuelve a analizar para comprobar que la góndola quedó repuesta."),
  h2("Cambio de alcance respecto a la Fase 1"),
  p("En la Fase 1 el foco estaba en el modelo de visión y en una alerta con semáforo. Al avanzar en la Fase 2 nos dimos cuenta de que una alerta por sí sola no asegura que alguien vaya a reponer, así que la alerta pasó a ser un ticket con responsable, estados, historial y cierre verificado. También agregamos la captura automática desde las cámaras. En la parte del modelo cambiamos la detección con bounding boxes (YOLO) por segmentación por píxel (SegFormer), porque entrega un porcentaje de vacío más preciso."),
  h1("5. Alcance"),
  tabla(["Incluye", "No incluye"], [
    ["Cálculo del % de vacío por góndola", "Reconocer cada producto de forma individual"],
    ["Tickets con prioridad, asignación y cierre verificado", "Integración con el sistema de inventario de Walmart"],
    ["App Android para reponedores", "App para iOS"],
    ["Panel web para supervisores y administradores", "Análisis de video en tiempo real (se trabaja con fotos fijas)"],
    ["Notificaciones push y sugerencia del producto faltante con IA", "Distinguir un vacío real de un espacio no apilable (queda como mejora)"],
  ], [4680, 4680]),
  h1("6. Restricciones"),
  bullet("Entrenamiento con un máximo de 4 GB de VRAM (Google Colab / Kaggle)."),
  bullet("Inferencia sin GPU. Walmart pidió entre 2 y 5 segundos por imagen y nosotros nos pusimos como meta 3 segundos."),
  bullet("El sistema tiene que poder instalarse en otro equipo siguiendo solo el manual (Docker Compose)."),
  bullet("Los datasets externos deben tener licencia que permita uso académico y comercial."),
  bullet("Un semestre de plazo (agosto a noviembre de 2026) y un equipo de 3 personas."),
  h1("7. Riesgos"),
  p("Los riesgos los levantamos en la Fase 1 en la Matriz de Riesgo (22 riesgos). En la tabla están los más importantes y cómo terminaron."),
  tabla(["#", "Riesgo", "Prob.", "Impacto", "Qué hicimos", "Estado"], [
    ["3", "Dataset de Walmart insuficiente o poco representativo", "Alta", "Alto", "Sacamos fotos propias en terreno (2 y 5 de octubre), sumamos datasets públicos con licencia y aplicamos data augmentation.", "Mitigado"],
    ["6", "Etiquetado inconsistente entre integrantes", "Alta", "Alto", "Definimos un formato único desde el inicio y después pasamos a máscaras de segmentación.", "Mitigado"],
    ["9", "El modelo no generaliza a condiciones reales de sala", "Alta", "Alto", "Entrenamos con fotos reales y dejamos el umbral configurable por recinto.", "En seguimiento"],
    ["11", "Inferencia sobre 2–5 s por imagen", "Baja", "Medio", "Exportamos a ONNX y medimos el p95 en cada versión: entre 1,1 y 2,0 s en CPU.", "Cerrado"],
    ["13", "Retraso en la retroalimentación de Walmart (ciclo de ~2 semanas)", "Media", "Medio", "Dejamos holguras en la Carta Gantt entre cada ciclo.", "Mitigado"],
    ["16", "Desalineación entre la salida del modelo y la aplicación", "Media", "Alto", "Fijamos el contrato de datos en la base (tabla prediccion) y en el manifiesto del modelo.", "Cerrado"],
    ["17", "Sobrecarga al desarrollar modelo y aplicación en paralelo", "Media", "Medio", "Separamos el trabajo por área: Ignacio en el modelo, Jesús en backend y web, Claudio en la app y la documentación.", "Mitigado"],
    ["19", "Documentación insuficiente para que un tercero ejecute el sistema", "Media", "Alto", "Manual de instalación con Docker Compose y un script único para la base de datos.", "Cerrado"],
    ["21", "Exponer información sensible en el repositorio", "Baja", "Alto", "Las claves quedan en .env y en la carpeta secretos/, ambas fuera del repo (.gitignore).", "Cerrado"],
  ], [450, 2400, 800, 900, 3560, 1250]),
  h1("8. Roles"),
  tabla(["Rol", "Quién", "Responsabilidad"], [
    ["Product Owner", "José Larraín (Walmart Chile, área de IA)", "Presentó el desafío en el kickoff, define lo que aporta valor y evalúa el modelo con el dataset de Walmart."],
    ["Docente guía / Jefe de proyecto", "Arturo Vargas (Duoc UC)", "Aprueba cada fase y nos retroalimenta en las consultas de los viernes."],
    ["Scrum Master", "Claudio Galiano", "Metodología, Carta Gantt, tablero en Jira, requerimientos y documentación (R/A en la Matriz RACI)."],
    ["Equipo de desarrollo", "Jesús González", "Backend, base de datos, panel web y despliegue."],
    ["Equipo de desarrollo", "Ignacio Ruz", "Datos, entrenamiento y evaluación del modelo de visión."],
    ["Equipo de desarrollo", "Claudio Galiano", "App Android y prototipos de interfaz (UI/UX)."],
  ], [2200, 2900, 4260]),
  h1("9. Metodología"),
  p("En la Fase 1 definimos un enfoque Kanban + CRISP-DM. CRISP-DM nos ordenó el trabajo del modelo (comprensión del negocio y de los datos, preparación, modelado y evaluación) y el seguimiento de actividades lo llevamos con la Carta Gantt."),
  p("Para esta entrega ordenamos el trabajo que hicimos durante el semestre en formato Scrum: épicas, historias de usuario priorizadas y sprints de 2 semanas. Elegimos 2 semanas porque es lo que dura el ciclo de evaluación de Walmart. Los sprints son una reconstrucción hecha al cierre a partir de la Gantt y del repositorio; agrupan el trabajo que efectivamente hicimos, pero no son sprints que hayamos creado en una herramienta durante el semestre."),
  p("El 10-11-2026 pasamos la Carta Gantt a un tablero en Jira (espacio StockEye, clave SKT) para ordenar el cierre del proyecto y tener el seguimiento en una herramienta compartida."),
  h2("Coordinación del equipo"),
  bullet("Reuniones de equipo los jueves y viernes."),
  bullet("Reuniones de 1 a 2 horas los fines de semana, y jornadas más largas antes de las entregas (el domingo 15-11 trabajamos más de 6 horas)."),
  bullet("Consultas con el profesor los viernes."),
  bullet("Comunicación diaria por WhatsApp y Discord."),
];

// ================= 2. Épicas, sprints e HU =================
const ptsEp = (e) => HU.filter((h) => h.ep === e).reduce((a, h) => a + h.pts, 0);
const ptsSp = (s) => HU.filter((h) => h.sprint === s).reduce((a, h) => a + h.pts, 0);
const epicas = [
  h1("1. Organización del backlog"),
  p("El backlog lo armamos en tres niveles: épicas (objetivos grandes), historias de usuario (lo que necesita cada rol) y sprints de 2 semanas. Las historias las estimamos en puntos usando Fibonacci (1, 2, 3, 5, 8) y cada una está enlazada con sus casos de uso y con las tareas del tablero de Jira (SKT-n)."),
  p("Los sprints son una reconstrucción hecha al cierre del proyecto: agrupamos por quincena el trabajo que muestran la Carta Gantt y el repositorio."),
  h1("2. Evolución desde la Fase 1"),
  p("En la Fase 1 teníamos 5 épicas y 16 historias (de HU-G01 a HU-M04), una por caso de uso y pensadas para alertas con semáforo. Cuando cambiamos a tickets de reposición reescribimos el backlog. En esta tabla se ve qué pasó con cada historia original."),
  tabla(["HU Fase 1", "Historia original", "HU Fase 2", "Qué cambió"], [
    ["HU-G01", "Iniciar sesión según rol", "HU-08", "Se mantiene, ahora con JWT y renovación del token."],
    ["HU-R01", "Ver mapa de mi zona", "HU-16", "El mapa se cambió por la lista Mis tickets."],
    ["HU-R02", "Recibir alerta de quiebre", "HU-20", "La alerta pasó a ser una notificación push del ticket."],
    ["HU-R03", "Marcar alerta en atención", "HU-16", "Ahora es el botón Empezar (estado EN PROGRESO)."],
    ["HU-R04", "Marcar alerta resuelta", "HU-17", "Para cerrar hay que tomar una foto de verificación."],
    ["HU-S01", "Ver mapa completo de góndolas", "HU-14", "Se reemplazó por la bandeja de tickets."],
    ["HU-S02", "Priorizar y asignar alertas", "HU-13, HU-15", "La prioridad es automática y al asignar se ve la carga de cada reponedor."],
    ["HU-S03", "Configurar umbral (30 %)", "HU-23", "Umbral por recinto (5 % por defecto), lo configura el administrador."],
    ["HU-S04", "Reportes de desempeño", "HU-22", "Se mantiene."],
    ["HU-A01", "Gestionar el modelo", "HU-26", "Versiones ONNX que se pueden activar y revertir."],
    ["HU-A02", "Administrar la base de datos", "HU-07", "Reglas en la base, migraciones y respaldos."],
    ["HU-A03", "Gestionar el repositorio", "HU-29, HU-30", "Pasa a ser práctica del equipo y parte de la entrega final."],
    ["HU-M01", "Capturar imagen periódica", "HU-09", "Capturador por recinto que se autentica con API key."],
    ["HU-M02", "Detectar vacíos (bounding box)", "HU-04, HU-05", "Se cambió a segmentación con SegFormer."],
    ["HU-M03", "Calcular % de vacío por carril", "HU-05, HU-06", "El % se calcula por góndola, en ≤ 3 s."],
    ["HU-M04", "Generar alerta automática", "HU-12, HU-13", "Pasa a ticket automático con prioridad."],
  ], [1100, 2700, 1400, 4160]),
  h1("3. Épicas"),
  tabla(["ID", "Épica", "Objetivo", "Épica en Jira", "Responsable", "Pts"], S.EPICAS.map((e) => [e[0], e[1], e[2], e[3], e[4], String(ptsEp(e[0]))]), [800, 1700, 2900, 1500, 1660, 800]),
  salto(),
  h1("4. Sprints"),
  tabla(["Sprint", "Período", "Objetivo", "Historias", "Pts"], S.SPRINTS.map((s) => [s[0], s[1], s[2], s[3].join(", "), String(ptsSp(s[0]))]), [1000, 1500, 3700, 2260, 900]),
  imagen(path.join(IMG, "scrum_velocidad.png"), 624),
  leyenda("Figura 1. Puntos por sprint y burndown del backlog (156 puntos en total)."),
  p("Los primeros sprints tienen menos puntos porque estuvieron dedicados al análisis y a los datos, que en CRISP-DM son la base para poder entrenar. Desde el sprint 4, con el modelo funcionando, pasamos a construir el sistema y la velocidad sube."),
  salto(),
  h1("5. Historias de usuario"),
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
  h1("6. Trazabilidad"),
  tabla(["Historia", "Casos de uso", "Tareas en Jira"], HU.map((h) => [h.id, h.cu, h.jira]), [1400, 3000, 4960]),
];

// ================= 3. Priorización =================
const orden = [...HU].sort((a, c) => ({ Must: 0, Should: 1, Could: 2 }[a.mos] - { Must: 0, Should: 1, Could: 2 }[c.mos]) || (c.valor / c.pts - a.valor / a.pts));
const cuenta = (m) => HU.filter((h) => h.mos === m).length;
const priorizacion = [
  h1("1. Método"),
  p("Para priorizar usamos MoSCoW. Cada historia quedó como Must (sin ella el sistema no cumple su objetivo), Should (importante, pero el sistema funciona igual), Could (deseable si alcanza el tiempo) o Won't (queda fuera de este semestre)."),
  p("Dentro de cada grupo ordenamos por valor/esfuerzo: el valor para el negocio de 1 a 5, según lo conversado con el cliente, dividido por los puntos de historia. Además respetamos las dependencias técnicas: sin datos no hay modelo, sin modelo no hay tickets automáticos y sin login no hay app ni panel."),
  h1("2. Resultado MoSCoW"),
  tabla(["Categoría", "Historias", "En StockEye"], [
    ["Must", String(cuenta("Must")), "Detectar el vacío, abrir el ticket, asignarlo, atenderlo y cerrarlo con foto. Es el núcleo del producto."],
    ["Should", String(cuenta("Should")), "Notificaciones push, reportes, comentarios, edición de tickets y prototipos."],
    ["Could", String(cuenta("Could")), "Sugerencia del producto faltante con IA."],
    ["Won't (este semestre)", "—", "Distinguir vacío real de espacio no apilable, app iOS e integración con inventario."],
  ], [2000, 1200, 6160]),
  salto(),
  h1("3. Backlog priorizado"),
  tabla(["#", "ID", "Historia (resumen)", "MoSCoW", "Valor", "Pts", "Valor/Pts", "Sprint"],
    orden.map((h, i) => [String(i + 1), h.id, `${h.rol[0].toUpperCase() + h.rol.slice(1)}: ${h.quiero}`, h.mos, String(h.valor), String(h.pts), (h.valor / h.pts).toFixed(2), h.sprint.replace("Sprint ", "S")]),
    [450, 800, 3810, 950, 750, 600, 1000, 1000]),
  h1("4. Observaciones"),
  bullet("Las historias de datos y modelo (EP-01) son Must y fueron las primeras, aunque su valor/esfuerzo es bajo, porque todo lo demás depende de ellas."),
  bullet("La sugerencia de producto con IA quedó como Could. Aporta, pero el sistema cumple su objetivo sin ella, por eso se puede desactivar."),
  bullet("Las notificaciones push quedaron como Should. El panel ya se actualiza en tiempo real, pero el reponedor necesita el aviso en el celular."),
];

module.exports = { analisis, epicas, priorizacion, HU, S, historia };
if (require.main === module) Promise.all([
  documento("StockEye_Analisis_del_Caso.docx", "Análisis del caso", "Documentación SCRUM", analisis),
  documento("StockEye_Epicas_Sprints_HU.docx", "Épicas, Sprints y Historias de Usuario", "Documentación SCRUM", epicas),
  documento("StockEye_Priorizacion_HU.docx", "Priorización de Historias de Usuario", "Documentación SCRUM", priorizacion),
]).catch((e) => { console.error(e); process.exit(1); });
