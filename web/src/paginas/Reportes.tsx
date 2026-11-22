import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Cargando, cx, EstadoVacio, Seccion } from "../componentes/ui";
import { api } from "../lib/api";
import { duracion, pct } from "../lib/formato";
import { useRecinto } from "../lib/sesion";

interface Reporte {
  dias: number;
  por_dia: { dia: string; abiertos: number; cerrados: number }[];
  totales: {
    tickets: number; cerrados: number; cerrados_verificados: number;
    minutos_promedio_cierre: number | null; minutos_promedio_asignacion: number | null; vacio_promedio: string | null;
  };
  por_categoria: { categoria: string; tickets: number; vacio_promedio: string | null }[];
}

// Paleta categórica validada (scripts/validate_palette.js): slot 1 azul, slot 2 naranjo.
const SERIES = [
  { clave: "abiertos" as const, nombre: "Abiertos", color: "#2a78d6" },
  { clave: "cerrados" as const, nombre: "Cerrados", color: "#eb6834" },
];

function dia(iso: string) {
  const [, m, d] = iso.split("-");
  return `${Number(d)}/${Number(m)}`;
}

function Grafico({ datos }: { datos: Reporte["por_dia"] }) {
  const [hover, setHover] = useState<number | null>(null);
  const maximo = Math.max(1, ...datos.flatMap((d) => [d.abiertos, d.cerrados]));
  const paso = maximo <= 5 ? 1 : Math.ceil(maximo / 4);
  const tope = Math.ceil(maximo / paso) * paso;
  const marcas = Array.from({ length: tope / paso + 1 }, (_, i) => i * paso);
  const alto = 220;
  return (
    <div className="relative">
      <div className="mb-3 flex gap-4 text-sm text-slate-700" aria-hidden>
        {SERIES.map((s) => (
          <span key={s.clave} className="flex items-center gap-2">
            <span className="size-3 rounded-sm" style={{ background: s.color }} /> {s.nombre}
          </span>
        ))}
      </div>
      <div className="flex gap-2">
        <div className="relative w-8 shrink-0 text-right text-xs text-slate-500" style={{ height: alto }}>
          {marcas.map((m) => (
            <span key={m} className="absolute right-0 -translate-y-1/2 tabular-nums" style={{ bottom: `${(m / tope) * 100}%` }}>{m}</span>
          ))}
        </div>
        <div className="relative flex-1 overflow-x-auto">
          <div className="relative" style={{ height: alto, minWidth: datos.length * 28 }}>
            {marcas.map((m) => (
              <div key={m} className="absolute inset-x-0 border-t border-slate-100" style={{ bottom: `${(m / tope) * 100}%` }} />
            ))}
            <div className="absolute inset-0 flex items-end">
              {datos.map((d, i) => (
                <div
                  key={d.dia}
                  className={cx("relative flex h-full flex-1 items-end justify-center gap-[2px] px-[3px]", hover === i && "bg-slate-50")}
                  onMouseEnter={() => setHover(i)}
                  onMouseLeave={() => setHover(null)}
                  onFocus={() => setHover(i)}
                  onBlur={() => setHover(null)}
                  tabIndex={0}
                  aria-label={`${dia(d.dia)}: ${d.abiertos} abiertos, ${d.cerrados} cerrados`}
                >
                  {SERIES.map((s) => (
                    <div
                      key={s.clave}
                      className="w-full max-w-3.5 rounded-t-[4px]"
                      style={{ height: `${(d[s.clave] / tope) * 100}%`, background: s.color, minHeight: d[s.clave] ? 2 : 0 }}
                    />
                  ))}
                  {hover === i && (
                    <div className="pointer-events-none absolute bottom-full z-10 mb-2 w-max rounded-lg bg-slate-900 px-3 py-2 text-xs text-white shadow-lg">
                      <p className="font-semibold">{dia(d.dia)}</p>
                      {SERIES.map((s) => (
                        <p key={s.clave} className="flex items-center gap-2">
                          <span className="size-2 rounded-sm" style={{ background: s.color }} /> {s.nombre}: <b>{d[s.clave]}</b>
                        </p>
                      ))}
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>
          <div className="mt-1 flex text-[11px] text-slate-500" style={{ minWidth: datos.length * 28 }}>
            {datos.map((d, i) => (
              <span key={d.dia} className="flex-1 text-center">{i % Math.ceil(datos.length / 10) === 0 ? dia(d.dia) : ""}</span>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

function Indicador({ titulo, valor, detalle }: { titulo: string; valor: string; detalle?: string }) {
  return (
    <div className="tarjeta p-4">
      <p className="text-sm text-slate-600">{titulo}</p>
      <p className="font-display mt-1 text-3xl font-bold tabular-nums">{valor}</p>
      {detalle && <p className="mt-1 text-xs text-slate-500">{detalle}</p>}
    </div>
  );
}

export function Reportes() {
  const recinto = useRecinto();
  const [dias, setDias] = useState(14);
  const [tabla, setTabla] = useState(false);
  const { data, isLoading } = useQuery({
    queryKey: ["reporte", recinto?.id, dias],
    queryFn: () => api<Reporte>("/reportes", { consulta: { recinto_id: recinto?.id, dias } }),
    enabled: Boolean(recinto),
  });
  if (!recinto) return <EstadoVacio titulo="Elige un recinto" />;
  const t = data?.totales;
  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold">Reportes</h1>
          <p className="mt-1 text-sm text-slate-600">{recinto.nombre}</p>
        </div>
        <div className="flex rounded-lg border border-slate-300 bg-white p-1" role="group" aria-label="Período">
          {[7, 14, 30, 90].map((d) => (
            <button key={d} onClick={() => setDias(d)} aria-pressed={dias === d}
              className={cx("rounded-md px-3 py-1.5 text-sm font-medium", dias === d ? "bg-slate-900 text-white" : "text-slate-600")}>
              {d} días
            </button>
          ))}
        </div>
      </div>
      {isLoading || !data ? (
        <Cargando />
      ) : (
        <>
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <Indicador titulo="Tickets" valor={String(t?.tickets ?? 0)} detalle={`${t?.cerrados ?? 0} cerrados`} />
            <Indicador titulo="Cierres verificados" valor={t?.cerrados ? `${Math.round((100 * t.cerrados_verificados) / t.cerrados)} %` : "—"}
              detalle="con foto bajo el umbral" />
            <Indicador titulo="Tiempo a asignar" valor={duracion(t?.minutos_promedio_asignacion)} detalle="promedio" />
            <Indicador titulo="Tiempo a cerrar" valor={duracion(t?.minutos_promedio_cierre)} detalle={`vacío promedio ${pct(t?.vacio_promedio ?? null)}`} />
          </div>
          <Seccion titulo="Tickets por día" extra={
            <button className="text-sm font-medium text-primario" onClick={() => setTabla((x) => !x)}>{tabla ? "Ver gráfico" : "Ver tabla"}</button>
          }>
            <div className="p-5">
              {tabla ? (
                <table className="w-full text-sm">
                  <thead><tr><th className="tabla-cabecera">Día</th><th className="tabla-cabecera">Abiertos</th><th className="tabla-cabecera">Cerrados</th></tr></thead>
                  <tbody>
                    {data.por_dia.map((d) => (
                      <tr key={d.dia} className="border-t border-slate-100"><td className="px-4 py-2">{dia(d.dia)}</td><td className="px-4 py-2 tabular-nums">{d.abiertos}</td><td className="px-4 py-2 tabular-nums">{d.cerrados}</td></tr>
                    ))}
                  </tbody>
                </table>
              ) : (
                <Grafico datos={data.por_dia} />
              )}
            </div>
          </Seccion>
          <Seccion titulo="Por categoría">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead><tr><th className="tabla-cabecera">Categoría</th><th className="tabla-cabecera">Tickets</th><th className="tabla-cabecera">Vacío promedio</th></tr></thead>
                <tbody>
                  {data.por_categoria.map((c) => (
                    <tr key={c.categoria} className="border-t border-slate-100">
                      <td className="px-4 py-2.5 font-medium">{c.categoria}</td>
                      <td className="px-4 py-2.5 tabular-nums">{c.tickets}</td>
                      <td className="px-4 py-2.5 tabular-nums">{pct(c.vacio_promedio)}</td>
                    </tr>
                  ))}
                  {!data.por_categoria.length && <tr><td colSpan={3} className="px-4 py-6 text-center text-slate-500">Sin tickets en el período</td></tr>}
                </tbody>
              </table>
            </div>
          </Seccion>
        </>
      )}
    </div>
  );
}
