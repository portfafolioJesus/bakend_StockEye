import { useQuery } from "@tanstack/react-query";
import { Avatar, Cargando, cx, EstadoVacio, Seccion } from "../componentes/ui";
import { api } from "../lib/api";
import { hace } from "../lib/formato";
import { useRecinto } from "../lib/sesion";
import type { Carga } from "../lib/tipos";

export function Equipo() {
  const recinto = useRecinto();
  const { data = [], isLoading } = useQuery({
    queryKey: ["equipo", recinto?.id],
    queryFn: () => api<Carga[]>(`/recintos/${recinto?.id}/equipo`),
    enabled: Boolean(recinto),
  });
  if (!recinto) return <EstadoVacio titulo="Elige un recinto" />;
  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-3xl font-bold">Equipo</h1>
        <p className="mt-1 text-sm text-slate-600">Reponedores de {recinto.nombre} y su carga de trabajo</p>
      </div>
      <Seccion titulo={`Reponedores · ${data.length}`}>
        {isLoading ? <Cargando /> : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[620px]">
              <thead>
                <tr>
                  <th className="tabla-cabecera">Nombre</th>
                  <th className="tabla-cabecera">Asignados</th>
                  <th className="tabla-cabecera">En progreso</th>
                  <th className="tabla-cabecera">Cerrados hoy</th>
                  <th className="tabla-cabecera">Último acceso</th>
                </tr>
              </thead>
              <tbody>
                {data.map((u) => {
                  const activos = u.asignados + u.en_progreso;
                  return (
                    <tr key={u.usuario_id} className="border-t border-slate-100">
                      <td className="px-4 py-3">
                        <span className="flex items-center gap-3">
                          <Avatar nombre={u.reponedor} tamano="sm" />
                          <span className="font-semibold">{u.reponedor}</span>
                          {!activos && <span className="rounded-full bg-green-50 px-2 py-0.5 text-xs font-semibold text-green-700">libre</span>}
                        </span>
                      </td>
                      <td className="px-4 py-3 tabular-nums">{u.asignados}</td>
                      <td className={cx("px-4 py-3 tabular-nums", u.en_progreso > 0 && "font-semibold text-violet-700")}>{u.en_progreso}</td>
                      <td className="px-4 py-3 tabular-nums">{u.cerrados_hoy}</td>
                      <td className="px-4 py-3 text-sm text-slate-600">{hace(u.ultimo_acceso)}{u.ultimo_acceso_origen === "app" ? " · app" : ""}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </Seccion>
    </div>
  );
}
