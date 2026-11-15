import { useQuery } from "@tanstack/react-query";
import { ImagePlus } from "lucide-react";
import { useState } from "react";
import { Diagnostico } from "../componentes/Diagnostico";
import { SubirFotos } from "../componentes/SubirFotos";
import { Boton, Cargando, EstadoVacio, Seccion } from "../componentes/ui";
import { api } from "../lib/api";
import { hace, hora } from "../lib/formato";
import { useRecinto } from "../lib/sesion";
import type { Camara, Gondola } from "../lib/tipos";

export function EstadoCamara({ c }: { c: Camara }) {
  return c.en_linea ? (
    <span className="inline-flex items-center gap-2 text-sm font-semibold text-green-700"><span className="size-2 rounded-full bg-green-600" />En línea</span>
  ) : (
    <span className="inline-flex items-center gap-2 text-sm font-semibold text-vacio"><span className="size-2 rounded-full bg-marca" />{c.activa ? "Sin señal" : "Desactivada"}</span>
  );
}

export function Gondolas() {
  const recinto = useRecinto();
  const [diag, setDiag] = useState<number | null>(null);
  const [subir, setSubir] = useState(false);
  const { data: camaras = [], isLoading } = useQuery({
    queryKey: ["camaras", recinto?.id],
    queryFn: () => api<Camara[]>(`/recintos/${recinto?.id}/camaras`),
    enabled: Boolean(recinto),
    refetchInterval: 60_000,
  });
  const { data: gondolas = [] } = useQuery({
    queryKey: ["gondolas", recinto?.id],
    queryFn: () => api<Gondola[]>(`/recintos/${recinto?.id}/gondolas`),
    enabled: Boolean(recinto),
  });
  if (!recinto) return <EstadoVacio titulo="Elige un recinto" />;
  const enLinea = camaras.filter((c) => c.en_linea).length;
  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold">Góndolas y cámaras</h1>
          <p className="mt-1 text-sm text-slate-600">{recinto.nombre} · {enLinea} de {camaras.length} cámaras en línea · fotos en <code>{recinto.carpeta_imagenes}</code></p>
        </div>
        <Boton variante="secundario" onClick={() => setSubir(true)}><ImagePlus className="size-4" /> Subir fotos</Boton>
      </div>
      <Seccion titulo={`Cámaras · ${camaras.length}`}>
        {isLoading ? <Cargando /> : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[640px]">
              <thead><tr><th className="tabla-cabecera">Código</th><th className="tabla-cabecera">Góndola</th><th className="tabla-cabecera">Estado</th><th className="tabla-cabecera">Última foto</th><th className="tabla-cabecera">Frecuencia</th></tr></thead>
              <tbody>
                {camaras.map((c) => (
                  <tr key={c.id} className={c.en_linea ? "border-t border-slate-100" : "border-t border-slate-100 bg-orange-50/50"}>
                    <td className="px-4 py-3 font-semibold">{c.codigo}</td>
                    <td className="px-4 py-3">{c.gondola_codigo} · {c.categoria}</td>
                    <td className="px-4 py-3"><EstadoCamara c={c} /></td>
                    <td className="px-4 py-3 text-sm">{hora(c.ultima_captura)}{!c.en_linea && c.ultima_captura && <span className="text-vacio"> · {hace(c.ultima_captura)}</span>}</td>
                    <td className="px-4 py-3 text-sm">
                      {c.en_linea ? `cada ${Math.round(c.intervalo_captura_seg / 60)} min` : <Boton variante="secundario" tamano="sm" onClick={() => setDiag(c.id)}>Diagnosticar</Boton>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Seccion>
      <Seccion titulo={`Góndolas · ${gondolas.length}`}>
        <ul className="grid gap-px bg-slate-100 sm:grid-cols-2 lg:grid-cols-3">
          {gondolas.map((g) => (
            <li key={g.id} className="bg-white px-5 py-3">
              <p className="font-semibold">{g.codigo}</p>
              <p className="text-sm text-slate-600">Pasillo {g.pasillo} · {g.categoria}{g.camara_codigo ? ` · ${g.camara_codigo}` : " · sin cámara (solo fotos de la app)"}</p>
            </li>
          ))}
        </ul>
      </Seccion>
      <Diagnostico camaraId={diag} onCerrar={() => setDiag(null)} />
      <SubirFotos abierto={subir} onCerrar={() => setSubir(false)} recintoId={recinto.id} carpeta={recinto.carpeta_imagenes} />
    </div>
  );
}
