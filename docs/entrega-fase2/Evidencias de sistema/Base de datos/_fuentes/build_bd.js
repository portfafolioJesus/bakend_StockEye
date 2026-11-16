const fs = require("fs");
const path = require("path");
const { Paragraph, TextRun, Table, TableRow, WidthType } = require("docx");
const L = require("./lib.js");
const { p, h1, h2, bullet, salto, celda, tabla, imagen, leyenda, documento, ANCHO } = L;

const B = JSON.parse(fs.readFileSync(path.join(__dirname, "bd.json"), "utf8"));
const IMG = path.join(__dirname, "img");
const GRUPOS = ["Maestros", "Detección", "Tickets", "IA y notificaciones"];
const tablasDe = (g) => Object.keys(B.tablas).filter((t) => B.tablas[t][0] === g);
const code = (t) => new TextRun({ text: t, font: "Consolas", size: 20 });

// ---------- Diccionario ----------
function fixDefault(c) {
  if (c.col === "numero") return "INC + correlativo de 6 dígitos";
  return c.default.replace(/^'(.*)'$/, "$1");
}
const dic = [
  h1("1. Introducción"),
  p("Este diccionario describe cada tabla y columna de la base de datos de StockEye. La base es PostgreSQL 16 y se crea con las migraciones 001 a 004 del repositorio (carpeta db/migraciones). Los datos se sacaron directamente de una base creada con esas migraciones, así que coinciden con el código."),
  p(`En total hay ${Object.keys(B.esquema).length} tablas, 3 vistas, 11 tipos enumerados y 14 triggers. Las tablas se agrupan en cuatro áreas:`),
  ...GRUPOS.map((g) => bullet([new TextRun({ text: g + ": ", bold: true }), new TextRun(tablasDe(g).join(", "))])),
  h2("1.1 Convenciones"),
  bullet("Nombres en minúscula y en singular (ticket, gondola). Las claves primarias se llaman id."),
  bullet("Las claves foráneas terminan en _id o indican el rol (asignado_a, cerrado_por)."),
  bullet("Las fechas usan timestamptz (con zona horaria) y terminan en _en (creado_en, cerrado_en)."),
  bullet("Columnas de clave: PK = clave primaria, FK = clave foránea (indica la tabla), UQ = valor único."),
  h2("1.2 Tipos enumerados"),
  tabla(["Tipo", "Valores posibles"], Object.entries(require("./bd_enum.json")), [3000, 6360]),
  ...GRUPOS.flatMap((g, gi) => [
    salto(),
    h1(`${gi + 2}. ${g}`),
    ...tablasDe(g).flatMap((t) => [
      h2(t),
      p(B.tablas[t][1]),
      tabla(["Columna", "Tipo", "Nulo", "Clave", "Por defecto", "Descripción"],
        B.esquema[t].map((c) => [c.col, c.tipo, c.nulo, c.claves, fixDefault(c), c.desc]),
        [1700, 1350, 650, 1250, 1300, 3110]),
      ...(B.ck[t] ? [p([new TextRun({ text: "Reglas (CHECK): ", bold: true, size: 20 }), new TextRun({ text: B.ck[t].map((x) => x.replace(/::[\w ]+/g, "").replace(/^CHECK /, "")).join("  ·  "), size: 18 })], { spacing: { before: 80, after: 200 } })] : [new Paragraph({ spacing: { after: 200 }, children: [] })]),
    ]),
  ]),
  salto(),
  h1("6. Vistas, funciones y triggers"),
  h2("6.1 Vistas"),
  tabla(["Vista", "Para qué sirve"], [
    ["v_ticket_resumen", "Ticket con nombres de recinto, góndola y usuarios, listo para la bandeja del panel."],
    ["v_carga_reponedor", "Cantidad de tickets activos por reponedor (tarjeta Equipo de turno)."],
    ["v_camara_estado", "Estado de cada cámara: en línea o sin señal según su última captura."],
  ], [2600, 6760]),
  h2("6.2 Reglas que viven en la base de datos"),
  tabla(["Función / trigger", "Qué hace"], [
    ["fn_ticket_desde_prediccion", "Si la predicción supera el umbral, abre un ticket o agrega la foto como seguimiento a uno abierto."],
    ["fn_prioridad_por_vacio", "Calcula la prioridad: <10 % BAJA, ≥10 % MEDIA, ≥20 % ALTA, ≥40 % CRÍTICA."],
    ["trg_ticket_reglas", "Valida transiciones de estado y que el reponedor asignado sea del mismo recinto."],
    ["trg_ticket_historial", "Registra en historial_ticket cada cambio de estado o asignación."],
    ["trg_ticket_cerrado_notificar / trg_comentario_notificar", "Crean notificaciones al cerrar un ticket o comentar."],
    ["fn_encolar_analisis_ia / fn_aplicar_analisis_ia", "Encolan la consulta a la IA y guardan el producto sugerido en el ticket."],
    ["fn_recuperar_imagenes", "Devuelve a la cola las fotos de un worker que se cayó (lease vencido)."],
    ["trg_evento_* (imagen, ticket, comentario, notificacion, tarea, modelo)", "Avisan por LISTEN/NOTIFY a los workers y al panel (tiempo real)."],
    ["trg_gondola_categoria / trg_imagen_categoria", "Mantienen sincronizada la categoría de producto."],
    ["trg_usuario_actualizado", "Actualiza la columna actualizado_en."],
  ], [3600, 5760]),
];

// ---------- Modelo lógico ----------
const REL = [
  ["Recinto", "Góndola", "1 : N", "Un recinto tiene muchas góndolas."],
  ["Recinto", "Usuario", "N : M", "Un usuario puede trabajar en varios recintos (tabla usuario_recinto)."],
  ["Categoría", "Góndola", "1 : N", "Una categoría clasifica muchas góndolas."],
  ["Góndola", "Cámara", "1 : N", "Una góndola puede tener varias cámaras."],
  ["Cámara", "Imagen", "1 : N", "Una cámara captura muchas fotos."],
  ["Usuario", "Imagen", "1 : N", "Un reponedor sube fotos desde el celular."],
  ["Imagen", "Predicción", "1 : N", "Una foto se analiza (una vez por versión de modelo)."],
  ["Modelo IA", "Predicción", "1 : N", "Una versión del modelo genera muchas predicciones."],
  ["Predicción", "Detección", "1 : N", "Una predicción contiene varias zonas detectadas."],
  ["Góndola", "Ticket", "1 : N", "Una góndola origina muchos tickets en el tiempo."],
  ["Usuario", "Ticket", "1 : N", "Un reponedor atiende muchos tickets."],
  ["Ticket", "Imagen", "N : M", "Un ticket tiene fotos de apertura, seguimiento y cierre (tabla ticket_imagen)."],
  ["Ticket", "Comentario", "1 : N", "Un ticket recibe muchos comentarios."],
  ["Ticket", "Historial", "1 : N", "Cada cambio del ticket queda registrado."],
  ["Ticket", "Análisis IA", "1 : N", "Un ticket puede tener sugerencias de la IA."],
  ["Usuario", "Notificación", "1 : N", "Un usuario recibe muchas notificaciones."],
  ["Usuario", "Dispositivo push", "1 : N", "Un usuario puede registrar varios celulares."],
];
const logico = [
  h1("Modelo lógico"),
  p("El modelo lógico muestra las entidades del negocio, sus atributos principales y cómo se relacionan, sin entrar en tipos de datos ni en detalles de implementación. Se construyó a partir del flujo del sistema: una cámara o un reponedor saca una foto de una góndola, el modelo la analiza y, si falta producto, se abre un ticket que un reponedor atiende."),
  imagen(path.join(IMG, "bd_modelo_logico.png"), 624, 640),
  leyenda("Figura 1. Modelo lógico de StockEye."),
  salto(),
  h2("Relaciones"),
  tabla(["Entidad", "Entidad", "Cardinalidad", "Significado"], REL, [1700, 1700, 1300, 4660]),
  h2("Decisiones de diseño"),
  bullet("Las relaciones N:M (usuario–recinto y ticket–imagen) se resuelven con tablas intermedias en el modelo relacional."),
  bullet("Las fotos y las predicciones se guardan aunque no generen ticket, para tener trazabilidad y poder medir el modelo."),
  bullet("Imagen, góndola y ticket llevan el recinto en la clave foránea compuesta, así la base impide mezclar datos de recintos distintos."),
];

// ---------- Modelo relacional ----------
const fks = Object.entries(B.fk).flatMap(([t, l]) => l.map(([cs, r]) => [t, cs.join(", "), r]));
const relacional = [
  h1("Modelo relacional"),
  p("El modelo relacional es la base de datos tal como está implementada en PostgreSQL 16: 20 tablas con sus claves primarias (PK) y foráneas (FK). En la página siguiente está el diagrama con las claves; el diagrama con todas las columnas y sus tipos va como imagen aparte (bd_modelo_relacional.png y .svg) y el detalle de cada columna está en el Diccionario de datos."),
  h2("Notación"),
  bullet("PK en negrita = clave primaria. FK en cursiva = clave foránea."),
  bullet("La línea termina en “pata de gallo” en el lado N (muchos) y en una barra en el lado 1."),
  bullet("Colores: azul = maestros, morado = detección, verde = tickets, naranjo = IA y notificaciones."),
  h2("Claves foráneas"),
  tabla(["Tabla", "Columna(s)", "Referencia a"], fks, [3000, 3360, 3000]),
];
const relacionalApaisado = [{ landscape: true, children: [h2("Diagrama del modelo relacional"), imagen(path.join(IMG, "bd_modelo_relacional_claves.png"), 860, 540), leyenda("Figura 1. Modelo relacional de StockEye (claves primarias y foráneas).")] }];

// ---------- NoSQL ----------
const nosql = [
  h1("Base de datos NoSQL"),
  p("StockEye no usa una base de datos NoSQL. Toda la información vive en PostgreSQL porque los datos centrales (tickets, usuarios, góndolas, fotos) están muy relacionados entre sí y necesitan reglas que se cumplan siempre: un ticket no puede asignarse a un reponedor de otro recinto, un ticket cerrado debe tener fecha de cierre, cada cambio debe quedar en el historial. Eso se resuelve mejor con claves foráneas, restricciones y transacciones de una base relacional."),
  p("Lo que sí usamos es el tipo JSONB de PostgreSQL para guardar datos semiestructurados, que es la misma idea de un documento en una base NoSQL. Así tenemos la flexibilidad de un documento sin agregar otro motor que haya que instalar y mantener."),
  h2("“Colecciones” en JSONB"),
  tabla(["Tabla.columna", "Qué guarda", "Ejemplo"], [
    ["modelo_ia.clases", "Clases que reconoce el modelo.", '{"0": "fondo", "1": "ocupado", "2": "vacio"}'],
    ["modelo_ia.parametros", "Parámetros de inferencia del manifiesto del modelo.", '{"lado": 1280, "modo": "completa", "hilos_recomendados": 2}'],
    ["modelo_ia.metricas", "Métricas de evaluación del modelo.", '{"epoca": 19, "iou_vacio": 0.3544, "iou_gondola": 0.8181}'],
    ["camara.roi", "Polígono de la zona de la góndola dentro del cuadro, normalizado de 0 a 1.", '[[0.1, 0.05], [0.9, 0.05], [0.9, 0.95], [0.1, 0.95]]'],
    ["analisis_ia.productos_faltantes", "Productos que la IA cree que faltan, con confianza.", '[{"producto": "Arroz grado 1, 1 kg", "confianza": 0.86}]'],
    ["tarea.payload", "Datos de cada tarea en segundo plano.", '{"imagen_id": 40, "ticket_id": 15}'],
  ], [2600, 3300, 3460]),
  h2("¿Cuándo convendría NoSQL?"),
  p("Si el sistema crece a muchos recintos y se quiere guardar el historial completo de detecciones por varios años para análisis, esa parte (solo lectura y mucho volumen) podría moverse a un almacén de documentos o de series de tiempo. Por ahora PostgreSQL cubre el volumen esperado."),
];

Promise.all([
  documento("StockEye_Diccionario_de_Datos.docx", "Diccionario de datos", "Tablas, columnas, tipos y reglas de la base PostgreSQL", dic),
  documento("StockEye_Modelo_Logico.docx", "Modelo lógico de datos", "Entidades y relaciones", logico),
  documento("StockEye_Modelo_Relacional.docx", "Modelo relacional", "Tablas, claves primarias y foráneas", relacional, relacionalApaisado),
  documento("StockEye_NoSQL_Colecciones.docx", "Base de datos NoSQL", "Por qué no se usa y cómo se guardan los datos semiestructurados", nosql),
]).catch((e) => { console.error(e); process.exit(1); });
