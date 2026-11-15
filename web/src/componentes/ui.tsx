import { Check, LoaderCircle, Sparkles, X } from "lucide-react";
import { createContext, useCallback, useContext, useEffect, useRef, useState, type ButtonHTMLAttributes, type ReactNode } from "react";
import { iniciales, NOMBRE_ESTADO, NOMBRE_PRIORIDAD, num, pct } from "../lib/formato";
import type { EstadoTicket, Numero, Prioridad } from "../lib/tipos";

const cx = (...c: (string | false | null | undefined)[]) => c.filter(Boolean).join(" ");
export { cx };

type Variante = "primario" | "secundario" | "contorno" | "peligro" | "fantasma" | "exito";
const VARIANTES: Record<Variante, string> = {
  primario: "bg-primario text-white hover:bg-primario-oscuro",
  secundario: "border border-slate-300 bg-white text-slate-800 hover:bg-slate-50",
  contorno: "border border-primario bg-white text-primario hover:bg-blue-50",
  peligro: "border border-red-200 bg-white text-red-700 hover:bg-red-50",
  fantasma: "text-slate-600 hover:bg-slate-100",
  exito: "bg-green-700 text-white hover:bg-green-800",
};

export function Boton({
  variante = "primario",
  cargando,
  tamano = "md",
  className,
  children,
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { variante?: Variante; cargando?: boolean; tamano?: "sm" | "md" }) {
  return (
    <button
      {...props}
      disabled={props.disabled || cargando}
      className={cx(
        "inline-flex items-center justify-center gap-2 rounded-lg font-semibold transition disabled:cursor-not-allowed disabled:opacity-50",
        tamano === "sm" ? "px-3 py-1.5 text-sm" : "px-4 py-2.5 text-sm",
        VARIANTES[variante],
        className,
      )}
    >
      {cargando && <LoaderCircle className="size-4 animate-spin" aria-hidden />}
      {children}
    </button>
  );
}

const ESTILO_ESTADO: Record<EstadoTicket, string> = {
  ABIERTO: "bg-slate-100 text-slate-700",
  ASIGNADO: "bg-indigo-50 text-indigo-700",
  EN_PROGRESO: "bg-violet-100 text-violet-700",
  CERRADO: "bg-green-50 text-green-700",
  CANCELADO: "bg-slate-100 text-slate-500 line-through",
};

export function ChipEstado({ estado, verificado }: { estado: EstadoTicket; verificado?: boolean }) {
  const cerradoOk = estado === "CERRADO";
  return (
    <span className={cx("inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-semibold whitespace-nowrap", ESTILO_ESTADO[estado])}>
      {cerradoOk && <Check className="size-3" aria-hidden />}
      {cerradoOk ? (verificado ? "Cerrado · verificado" : "Cerrado") : NOMBRE_ESTADO[estado]}
    </span>
  );
}

const COLOR_PRIORIDAD: Record<Prioridad, string> = {
  BAJA: "bg-slate-400",
  MEDIA: "bg-amber-500",
  ALTA: "bg-red-600",
  CRITICA: "bg-red-900 ring-2 ring-red-200",
};

export function Prioridad({ valor, conTexto = true }: { valor: Prioridad; conTexto?: boolean }) {
  return (
    <span className="inline-flex items-center gap-2 text-sm whitespace-nowrap">
      <span className={cx("size-2 rounded-full", COLOR_PRIORIDAD[valor])} aria-hidden />
      {conTexto && NOMBRE_PRIORIDAD[valor]}
    </span>
  );
}

/** % de vacío con barra; la barra se llena hasta 40 % (prioridad crítica). */
export function BarraVacio({ valor, hasta, umbral }: { valor: Numero; hasta?: Numero; umbral?: Numero }) {
  const n = num(valor) ?? 0;
  const fin = num(hasta);
  const bajo = fin !== null && fin <= (num(umbral) ?? 5);
  return (
    <div className="min-w-24">
      <div className="text-sm font-semibold whitespace-nowrap tabular-nums">
        {pct(valor)}
        {fin !== null && <span className={cx("ml-1", bajo ? "text-green-700" : "text-vacio")}>→ {pct(fin)}</span>}
      </div>
      <div className="mt-1 h-1.5 w-20 overflow-hidden rounded-full bg-slate-100">
        <div
          className={cx("h-full rounded-full", fin !== null ? (bajo ? "bg-green-600" : "bg-marca") : "bg-marca")}
          style={{ width: `${Math.min(100, ((fin ?? n) / 40) * 100)}%` }}
        />
      </div>
    </div>
  );
}

export function Avatar({ nombre, tamano = "md", oscuro }: { nombre: string; tamano?: "sm" | "md"; oscuro?: boolean }) {
  return (
    <span
      className={cx(
        "inline-flex shrink-0 items-center justify-center rounded-full font-semibold",
        tamano === "sm" ? "size-8 text-xs" : "size-10 text-sm",
        oscuro ? "bg-slate-700 text-white" : "bg-indigo-50 text-indigo-700",
      )}
      aria-hidden
    >
      {iniciales(nombre)}
    </span>
  );
}

export function ChipIA({ children }: { children: ReactNode }) {
  return (
    <span className="inline-flex items-center gap-1 text-xs font-medium text-ia">
      <Sparkles className="size-3" aria-hidden />
      {children}
    </span>
  );
}

export function Cargando({ texto = "Cargando…" }: { texto?: string }) {
  return (
    <div className="flex items-center justify-center gap-2 p-10 text-sm text-slate-500">
      <LoaderCircle className="size-4 animate-spin" aria-hidden />
      {texto}
    </div>
  );
}

export function EstadoVacio({ titulo, detalle, icono }: { titulo: string; detalle?: string; icono?: ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 p-10 text-center">
      {icono && <div className="text-slate-300">{icono}</div>}
      <p className="font-semibold text-slate-700">{titulo}</p>
      {detalle && <p className="max-w-sm text-sm text-slate-500">{detalle}</p>}
    </div>
  );
}

export function Modal({ abierto, titulo, onCerrar, children, ancho = "max-w-lg" }: {
  abierto: boolean;
  titulo: string;
  onCerrar: () => void;
  children: ReactNode;
  ancho?: string;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const d = ref.current;
    if (!d) return;
    if (abierto && !d.open) d.showModal();
    if (!abierto && d.open) d.close();
  }, [abierto]);
  return (
    <dialog
      ref={ref}
      onClose={onCerrar}
      className={cx("m-auto w-[calc(100%-2rem)] rounded-2xl p-0 shadow-2xl backdrop:bg-slate-900/50", ancho)}
    >
      {abierto && (
        <div className="p-6">
          <div className="mb-4 flex items-start justify-between gap-4">
            <h2 className="text-lg font-bold">{titulo}</h2>
            <button onClick={onCerrar} className="rounded-lg p-1 text-slate-500 hover:bg-slate-100" aria-label="Cerrar">
              <X className="size-5" />
            </button>
          </div>
          {children}
        </div>
      )}
    </dialog>
  );
}

// ---------------------------------------------------------------- avisos

interface Aviso {
  id: number;
  texto: string;
  tipo: "ok" | "error" | "info";
}
const CtxAvisos = createContext<(texto: string, tipo?: Aviso["tipo"]) => void>(() => {});

export function ProveedorAvisos({ children }: { children: ReactNode }) {
  const [avisos, setAvisos] = useState<Aviso[]>([]);
  const avisar = useCallback((texto: string, tipo: Aviso["tipo"] = "ok") => {
    const id = Date.now() + Math.random();
    setAvisos((a) => [...a.slice(-3), { id, texto, tipo }]);
    setTimeout(() => setAvisos((a) => a.filter((x) => x.id !== id)), tipo === "error" ? 7000 : 4000);
  }, []);
  return (
    <CtxAvisos.Provider value={avisar}>
      {children}
      <div className="fixed right-4 bottom-4 z-50 flex w-[min(24rem,calc(100%-2rem))] flex-col gap-2" aria-live="polite">
        {avisos.map((a) => (
          <div
            key={a.id}
            className={cx(
              "rounded-xl px-4 py-3 text-sm font-medium shadow-lg",
              a.tipo === "error" ? "bg-red-700 text-white" : a.tipo === "info" ? "bg-slate-900 text-white" : "bg-green-700 text-white",
            )}
          >
            {a.texto}
          </div>
        ))}
      </div>
    </CtxAvisos.Provider>
  );
}

export const useAvisos = () => useContext(CtxAvisos);

export function Seccion({ titulo, extra, children, className, id }: {
  titulo: ReactNode;
  extra?: ReactNode;
  children: ReactNode;
  className?: string;
  id?: string;
}) {
  return (
    <section id={id} className={cx("tarjeta scroll-mt-6", className)}>
      <div className="flex items-center justify-between gap-3 border-b border-slate-100 px-5 py-4">
        <h2 className="text-lg font-bold">{titulo}</h2>
        {extra}
      </div>
      {children}
    </section>
  );
}
