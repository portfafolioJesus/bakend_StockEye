// Cliente HTTP del panel: agrega el JWT, renueva la sesión una vez si expira
// y traduce los errores de la API a mensajes legibles.
const BASE = "/api/v1";
const CLAVE = "stockeye.sesion";

export interface Tokens {
  acceso: string;
  refresco: string;
}

export class ErrorApi extends Error {
  constructor(public status: number, mensaje: string) {
    super(mensaje);
  }
}

function leer(): Tokens | null {
  try {
    const t = localStorage.getItem(CLAVE);
    return t ? (JSON.parse(t) as Tokens) : null;
  } catch {
    return null;
  }
}

let tokens: Tokens | null = leer();
const oyentesSalida = new Set<() => void>();

export const sesion = {
  tokens: () => tokens,
  guardar(t: Tokens) {
    tokens = t;
    try {
      localStorage.setItem(CLAVE, JSON.stringify(t));
    } catch {
      /* modo privado: la sesión dura lo que la pestaña */
    }
  },
  cerrar() {
    tokens = null;
    try {
      localStorage.removeItem(CLAVE);
    } catch {
      /* sin almacenamiento */
    }
    oyentesSalida.forEach((f) => f());
  },
  alExpirar(f: () => void): () => void {
    oyentesSalida.add(f);
    return () => {
      oyentesSalida.delete(f);
    };
  },
};

let renovando: Promise<boolean> | null = null;

async function renovar(): Promise<boolean> {
  if (!tokens?.refresco) return false;
  renovando ??= (async () => {
    try {
      const r = await fetch(`${BASE}/auth/refresco`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refresco: tokens!.refresco }),
      });
      if (!r.ok) return false;
      sesion.guardar(await r.json());
      return true;
    } catch {
      return false;
    } finally {
      setTimeout(() => (renovando = null), 0);
    }
  })();
  return renovando;
}

type Consulta = Record<string, string | number | boolean | null | undefined>;

export interface Opciones {
  metodo?: "GET" | "POST" | "PATCH" | "PUT" | "DELETE";
  cuerpo?: unknown;
  form?: FormData;
  consulta?: Consulta;
}

function mensajeDe(datos: unknown, status: number): string {
  const d = (datos as { detail?: unknown })?.detail;
  if (typeof d === "string") return d;
  if (Array.isArray(d) && d.length) {
    const e = d[0] as { loc?: string[]; msg?: string };
    return `${e.loc?.slice(-1)[0] ?? "campo"}: ${e.msg ?? "inválido"}`;
  }
  if (status === 0) return "Sin conexión con el servidor";
  return `Error ${status}`;
}

export async function api<T = unknown>(ruta: string, op: Opciones = {}, reintento = true): Promise<T> {
  const url = new URL(BASE + ruta, window.location.origin);
  Object.entries(op.consulta ?? {}).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== "") url.searchParams.set(k, String(v));
  });
  const headers: Record<string, string> = {};
  if (tokens?.acceso) headers.Authorization = `Bearer ${tokens.acceso}`;
  let body: BodyInit | undefined;
  if (op.form) body = op.form;
  else if (op.cuerpo !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(op.cuerpo);
  }
  let r: Response;
  try {
    r = await fetch(url, { method: op.metodo ?? (body ? "POST" : "GET"), headers, body });
  } catch {
    throw new ErrorApi(0, "Sin conexión con el servidor");
  }
  if (r.status === 401 && reintento && tokens?.refresco && !ruta.startsWith("/auth/")) {
    if (await renovar()) return api<T>(ruta, op, false);
    sesion.cerrar();
  }
  if (r.status === 204) return undefined as T;
  const datos = await r.json().catch(() => null);
  if (!r.ok) throw new ErrorApi(r.status, mensajeDe(datos, r.status));
  return datos as T;
}
