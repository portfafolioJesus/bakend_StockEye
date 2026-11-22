import type { Numero, Prioridad, EstadoTicket, Rol } from "./tipos";

const ZONA = "America/Santiago";

export const num = (v: Numero | undefined): number | null => (v === null || v === undefined || v === "" ? null : Number(v));

export function pct(v: Numero | undefined, decimales = 1): string {
  const n = num(v);
  return n === null ? "—" : `${n.toLocaleString("es-CL", { minimumFractionDigits: decimales, maximumFractionDigits: decimales })} %`;
}

export function hora(iso: string | null | undefined): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleTimeString("es-CL", { hour: "2-digit", minute: "2-digit", timeZone: ZONA, hour12: false });
}

export function fechaHora(iso: string | null | undefined): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString("es-CL", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit", timeZone: ZONA, hour12: false });
}

export function duracion(minutos: number | null | undefined): string {
  if (minutos === null || minutos === undefined) return "—";
  if (minutos < 1) return "recién";
  if (minutos < 60) return `${minutos} min`;
  const h = Math.floor(minutos / 60);
  if (h < 24) return `${h} h ${minutos % 60 ? `${minutos % 60} min` : ""}`.trim();
  return `${Math.floor(h / 24)} d ${h % 24} h`;
}

/** Tiempo relativo corto: "ahora", "hace 25 min", "hace 2 h", "ayer", "hace 3 d". */
export function hace(iso: string | null | undefined): string {
  if (!iso) return "nunca";
  const min = Math.round((Date.now() - new Date(iso).getTime()) / 60000);
  if (min < 1) return "ahora";
  if (min < 60) return `hace ${min} min`;
  const h = Math.floor(min / 60);
  if (h < 24) return `hace ${h} h`;
  return h < 48 ? "ayer" : `hace ${Math.floor(h / 24)} d`;
}

export const iniciales = (nombre: string) =>
  nombre.split(" ").filter(Boolean).slice(0, 2).map((p) => p[0]?.toUpperCase()).join("");

export const NOMBRE_ESTADO: Record<EstadoTicket, string> = {
  ABIERTO: "Abierto",
  ASIGNADO: "Asignado",
  EN_PROGRESO: "En progreso",
  CERRADO: "Cerrado",
  CANCELADO: "Cancelado",
};

export const NOMBRE_PRIORIDAD: Record<Prioridad, string> = { BAJA: "Baja", MEDIA: "Media", ALTA: "Alta", CRITICA: "Crítica" };

export const NOMBRE_ROL: Record<Rol, string> = { ADMINISTRADOR: "Administrador", SUPERVISOR: "Supervisor", REPONEDOR: "Reponedor" };
