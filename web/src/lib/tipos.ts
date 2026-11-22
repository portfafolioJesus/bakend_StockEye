export type Rol = "ADMINISTRADOR" | "SUPERVISOR" | "REPONEDOR";
export type EstadoTicket = "ABIERTO" | "ASIGNADO" | "EN_PROGRESO" | "CERRADO" | "CANCELADO";
export type Prioridad = "BAJA" | "MEDIA" | "ALTA" | "CRITICA";
export type Numero = number | string | null; // NUMERIC llega como string

export interface RecintoCorto {
  id: number;
  codigo: string;
  nombre: string;
  carpeta_imagenes: string;
  umbral_vacio: Numero;
}

export interface Usuario {
  id: number;
  nombre: string;
  apellido: string;
  email: string;
  rol: Rol;
  debe_cambiar_clave: boolean;
  recintos: RecintoCorto[];
}

export interface TicketResumen {
  id: number;
  numero: string;
  titulo: string;
  estado: EstadoTicket;
  prioridad: Prioridad;
  origen: "CAMARA" | "MOVIL" | "MANUAL";
  porcentaje_vacio: Numero;
  producto_faltante: string | null;
  enriquecido_ia: boolean;
  recinto_id: number;
  recinto_codigo: string;
  gondola_id: number | null;
  gondola_codigo: string | null;
  pasillo: string | null;
  categoria: string | null;
  categoria_producto: string | null;
  descripcion: string | null;
  asignado_a: number | null;
  asignado_nombre: string | null;
  asignado_por_nombre: string | null;
  creado_por_nombre: string | null;
  creado_en: string;
  asignado_en: string | null;
  cerrado_en: string | null;
  minutos_abierto: number;
  num_comentarios: number;
  cierre_verificado: boolean;
  camara_codigo: string | null;
  pct_apertura: Numero;
  pct_cierre: Numero;
  umbral_vacio: Numero;
  camara_tipo: "IP" | "CARGA" | null;
}

export interface Conteos {
  sin_asignar: number;
  asignados: number;
  en_progreso: number;
  cerrados_hoy: number;
  cerrados_hoy_verificados: number;
  activos: number;
  todos: number;
  sin_asignar_mas_antiguo_min: number | null;
}

export interface Bandeja {
  total: number;
  conteos: Conteos;
  tickets: TicketResumen[];
}

export interface Carga {
  usuario_id: number;
  reponedor: string;
  asignados: number;
  en_progreso: number;
  cerrados_hoy: number;
  ultimo_acceso?: string | null;
  ultimo_acceso_origen?: string | null;
}

export interface Deteccion {
  clase: string;
  confianza: Numero;
  x_min: number;
  y_min: number;
  x_max: number;
  y_max: number;
}

export interface Evidencia {
  imagen_id: number;
  tipo: "APERTURA" | "SEGUIMIENTO" | "CIERRE";
  capturada_en: string;
  origen: "CAMARA" | "MOVIL";
  estado_imagen: string;
  ruta_archivo: string;
  camara_codigo: string | null;
  porcentaje_vacio: Numero;
  umbral_aplicado: Numero;
  supera_umbral: boolean | null;
  num_vacios: number | null;
  tiempo_inferencia_ms: number | null;
  modelo: string | null;
  subida_por_nombre: string | null;
  url: string | null;
  url_anotada: string | null;
  detecciones: Deteccion[];
}

export interface ProductoIA {
  producto: string;
  categoria?: string | null;
  confianza?: number;
}

export interface DetalleTicket {
  ticket: TicketResumen;
  evidencias: Evidencia[];
  comentarios: { id: number; usuario_id: number; nombre: string; rol: Rol; texto: string; creado_en: string }[];
  linea_tiempo: { en: string; tipo: string; texto: string }[];
  ia: { proveedor: string; modelo: string; productos_faltantes: ProductoIA[]; resumen: string | null; exitoso: boolean } | null;
  ia_pendiente: boolean;
  equipo: Carga[];
  permisos: Record<"asignar" | "editar" | "empezar" | "cerrar" | "cancelar" | "cambiar_estado" | "comentar", boolean>;
}

export interface Notificacion {
  id: number;
  tipo: string;
  mensaje: string;
  leida: boolean;
  creada_en: string;
  ticket_numero: string | null;
  incidente_ia_id?: number | null;
  recinto_id?: number | null;
}

export interface Alerta {
  numero: string;
  tipo: "APERTURA" | "SEGUIMIENTO";
  en: string;
  porcentaje_vacio: Numero;
  anterior: Numero;
  gondola_codigo: string | null;
  categoria: string | null;
}

export interface Camara {
  id: number;
  recinto_id: number;
  recinto_codigo: string;
  gondola_id: number | null;
  gondola_codigo: string | null;
  categoria: string | null;
  codigo: string;
  nombre: string | null;
  url_stream: string | null;
  intervalo_captura_seg: number;
  activa: boolean;
  ultima_captura: string | null;
  ultimo_error: string | null;
  en_linea: boolean;
}

export interface Categoria {
  id: number;
  codigo: string;
  nombre: string;
  departamento: string;
  tickets_activos?: number;
  puntos?: { id: number; codigo: string; descripcion: string | null }[];
}

export interface Gondola {
  categoria_id?: number | null;
  id: number;
  recinto_id?: number;
  codigo: string;
  pasillo: string | null;
  categoria: string | null;
  descripcion: string | null;
  activo?: boolean;
  camara_codigo?: string | null;
}


export type EstadoCaracterizacion = "NO_REQUERIDA" | "PENDIENTE" | "PROCESANDO" | "AUTOMATICA" | "MANUAL" | "REVISION";

export interface ImagenCaracterizacion {
  id: number;
  recinto_id: number;
  categoria_id: number | null;
  categoria: string | null;
  estado_caracterizacion: EstadoCaracterizacion;
  producto_caracterizado: string | null;
  version_caracterizacion: number;
  porcentaje_vacio: Numero;
  estado: "PENDIENTE" | "PROCESANDO" | "PROCESADA" | "ERROR";
  recibida_en: string;
  url_original: string | null;
  ticket_numero: string | null;
}

export interface IncidenciaIA {
  id: number;
  motivo: string;
  mensaje: string;
  reintentar_en: string | null;
  creada_en: string;
  pendientes: number;
}

export interface BandejaCaracterizacion {
  imagenes: ImagenCaracterizacion[];
  pendientes: number;
  total?: number;
  incidencias: IncidenciaIA[];
  categorias: Pick<Categoria, "id" | "codigo" | "nombre">[];
}
