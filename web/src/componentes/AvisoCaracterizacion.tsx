import { AlertTriangle } from "lucide-react";
import { Link } from "react-router";
import { fechaHora } from "../lib/formato";
import type { IncidenciaIA } from "../lib/tipos";

export function AvisoCaracterizacion({ incidencias, pendientes }: { incidencias: IncidenciaIA[]; pendientes: number }) {
  if (!incidencias.length) return null;
  const cuota = incidencias.some((i) => i.motivo === "CUOTA" || i.motivo === "CUOTA_AGOTADA");
  return (
    <section role="status" className="rounded-xl border border-amber-300 bg-amber-50 p-4 text-amber-950">
      <div className="flex items-start gap-3">
        <AlertTriangle className="mt-0.5 size-5 shrink-0" aria-hidden />
        <div className="min-w-0 flex-1">
          <h2 className="font-semibold">Caracterización automática pausada</h2>
          <p className="mt-1 text-sm">{cuota ? "La IA de caracterización alcanzó su cuota de uso." : "El servicio de caracterización alcanzó un límite de uso o está temporalmente indisponible."}</p>
          <p className="mt-1 text-sm">Hay <strong>{pendientes} imágenes pendientes</strong> en este recinto. El análisis de vacío continúa; puedes completar su categoría y producto manualmente.</p>
          <ul className="mt-2 space-y-1 text-xs text-amber-900">
            {incidencias.map((i) => <li key={i.id}>{i.mensaje}{i.reintentar_en ? ` · Reintento previsto: ${fechaHora(i.reintentar_en)}` : ""}</li>)}
          </ul>
          <Link to="/caracterizacion?estado=pendientes" className="mt-3 inline-flex rounded-lg border border-amber-400 bg-white px-3 py-2 text-sm font-semibold hover:bg-amber-100">Revisar imágenes pendientes</Link>
        </div>
      </div>
    </section>
  );
}
