import { useQuery } from "@tanstack/react-query";
import { api } from "../lib/api";
import { fechaHora, pct } from "../lib/formato";
import type { Camara } from "../lib/tipos";
import { Cargando, Modal } from "./ui";

interface Diag {
  camara: Camara;
  minutos_sin_foto: number | null;
  pasos: string[];
  ultimas_imagenes: { id: number; capturada_en: string; estado: string; porcentaje_vacio: string | null; error_detalle: string | null }[];
}

export function Diagnostico({ camaraId, onCerrar }: { camaraId: number | null; onCerrar: () => void }) {
  const { data, isLoading } = useQuery({
    queryKey: ["diagnostico", camaraId],
    queryFn: () => api<Diag>(`/admin/camaras/${camaraId}/diagnostico`),
    enabled: camaraId !== null,
  });
  return (
    <Modal abierto={camaraId !== null} titulo={`Diagnóstico ${data?.camara.codigo ?? ""}`} onCerrar={onCerrar} ancho="max-w-2xl">
      {isLoading || !data ? <Cargando /> : (
        <div className="flex flex-col gap-5">
          <ol className="flex list-decimal flex-col gap-2 pl-5 text-sm">
            {data.pasos.map((p) => <li key={p}>{p}</li>)}
          </ol>
          <div>
            <h3 className="mb-2 text-sm font-semibold">Últimas fotos recibidas</h3>
            <ul className="divide-y divide-slate-100 rounded-lg border border-slate-200 text-sm">
              {data.ultimas_imagenes.map((i) => (
                <li key={i.id} className="flex justify-between gap-3 px-3 py-2">
                  <span>{fechaHora(i.capturada_en)}</span>
                  <span className={i.estado === "ERROR" ? "text-red-700" : "text-slate-600"}>{i.estado === "PROCESADA" ? pct(i.porcentaje_vacio) : i.estado}</span>
                </li>
              ))}
              {!data.ultimas_imagenes.length && <li className="px-3 py-3 text-slate-500">Nunca envió fotos.</li>}
            </ul>
          </div>
        </div>
      )}
    </Modal>
  );
}
