import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Inbox, Search } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router";
import { Campana } from "../componentes/Campana";
import { Avatar, BarraVacio, Boton, Cargando, ChipEstado, ChipIA, cx, EstadoVacio, Prioridad, useAvisos } from "../componentes/ui";
import { api } from "../lib/api";
import { duracion, hora, pct } from "../lib/formato";
import { useRecinto, useSesion } from "../lib/sesion";
import type { Alerta, Bandeja as TBandeja, Carga, Prioridad as TPrioridad, TicketResumen } from "../lib/tipos";

type Vista = "todos" | "sin_asignar" | "asignados" | "en_progreso" | "cerrados_hoy";

function Tarjeta({ titulo, valor, detalle, destacada, onClick, activa }: {
  titulo: string; valor: number | undefined; detalle: string; destacada?: boolean; onClick: () => void; activa: boolean;
}) {
  return (
    <button
      onClick={onClick}
      aria-pressed={activa}
      className={cx(
        "rounded-xl border bg-white p-4 text-left transition hover:shadow-sm",
        destacada ? "border-orange-300 bg-marca-suave" : "border-slate-200",
        activa && "ring-2 ring-primario/30",
      )}
    >
      <p className={cx("text-sm font-medium", destacada ? "text-orange-800" : "text-slate-700")}>{titulo}</p>
      <p className="font-display mt-1 text-3xl font-bold tabular-nums">{valor ?? "–"}</p>
      <p className="mt-2 truncate text-xs text-slate-500">{detalle}</p>
    </button>
  );
}

function SelectorAsignar({ ticket, equipo, onListo }: { ticket: TicketResumen; equipo: Carga[]; onListo: () => void }) {
  const [abierto, setAbierto] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const qc = useQueryClient();
  const avisar = useAvisos();
  const asignar = useMutation({
    mutationFn: (usuario: Carga) => api(`/tickets/${ticket.numero}`, { metodo: "PATCH", cuerpo: { asignado_a: usuario.usuario_id } }),
    onSuccess: (_, u) => {
      avisar(`${ticket.numero} asignado a ${u.reponedor}. Recibirá una notificación push.`);
      qc.invalidateQueries({ queryKey: ["tickets"] });
      qc.invalidateQueries({ queryKey: ["equipo"] });
      setAbierto(false);
      onListo();
    },
    onError: (e: Error) => avisar(e.message, "error"),
  });
  useEffect(() => {
    const fuera = (e: MouseEvent) => ref.current && !ref.current.contains(e.target as Node) && setAbierto(false);
    document.addEventListener("mousedown", fuera);
    return () => document.removeEventListener("mousedown", fuera);
  }, []);
  return (
    <div className="relative" ref={ref}>
      <Boton variante="contorno" tamano="sm" onClick={() => setAbierto((a) => !a)}>
        Asignar
      </Boton>
      {abierto && (
        <div className="absolute right-0 z-20 mt-1 w-64 overflow-hidden rounded-xl border border-slate-200 bg-white shadow-xl">
          <p className="px-3 pt-3 pb-1 text-xs font-semibold text-slate-500 uppercase">Reponedores del recinto</p>
          {equipo.map((u) => {
            const activos = u.asignados + u.en_progreso;
            return (
              <button
                key={u.usuario_id}
                disabled={asignar.isPending}
                onClick={() => asignar.mutate(u)}
                className="flex w-full items-center justify-between gap-2 px-3 py-2 text-left text-sm hover:bg-slate-50"
              >
                <span className="font-medium">{u.reponedor}</span>
                <span className={cx("text-xs", activos ? "text-slate-500" : "font-semibold text-green-700")}>
                  {activos ? `${activos} activo${activos > 1 ? "s" : ""}` : "libre"}
                </span>
              </button>
            );
          })}
          {!equipo.length && <p className="px-3 py-3 text-sm text-slate-500">No hay reponedores activos en este recinto.</p>}
        </div>
      )}
    </div>
  );
}

function Fila({ t, equipo }: { t: TicketResumen; equipo: Carga[] }) {
  const ir = useNavigate();
  const origen =
    t.camara_tipo === "CARGA" ? "Foto cargada (carpeta o panel)" :
    t.origen === "CAMARA" ? `Cámara ${t.camara_codigo ?? ""}` : t.origen === "MOVIL" ? `Foto móvil · ${t.creado_por_nombre ?? ""}` : `Manual · ${t.creado_por_nombre ?? ""}`;
  return (
    <tr
      className={cx("cursor-pointer border-t border-slate-100 align-top hover:bg-slate-50/70", t.estado === "ABIERTO" && "bg-orange-50/40")}
      onClick={() => ir(`/tickets/${t.numero}`)}
    >
      <td className="min-w-56 px-4 py-3.5">
        <Link to={`/tickets/${t.numero}`} className="font-semibold text-primario hover:underline" onClick={(e) => e.stopPropagation()}>
          {t.numero}
        </Link>
        <p className="text-sm text-slate-800">{t.titulo}</p>
        <p className="text-xs text-slate-500">{origen}</p>
        {t.producto_faltante && t.enriquecido_ia && <ChipIA>IA: {t.producto_faltante}</ChipIA>}
      </td>
      <td className="px-4 py-3.5">
        <BarraVacio valor={t.estado === "CERRADO" ? t.pct_apertura : t.porcentaje_vacio} hasta={t.estado === "CERRADO" ? t.pct_cierre : null} umbral={t.umbral_vacio} />
      </td>
      <td className="px-4 py-3.5"><Prioridad valor={t.prioridad} /></td>
      <td className="px-4 py-3.5"><ChipEstado estado={t.estado} verificado={t.cierre_verificado} /></td>
      <td className="px-4 py-3.5 text-sm" onClick={(e) => t.estado === "ABIERTO" && e.stopPropagation()}>
        {t.estado === "ABIERTO" ? <SelectorAsignar ticket={t} equipo={equipo} onListo={() => undefined} /> : t.asignado_nombre ?? "—"}
      </td>
      <td className="px-4 py-3.5 text-sm whitespace-nowrap text-slate-600">
        {t.estado === "CERRADO" ? `cerrado ${hora(t.cerrado_en)}` : duracion(t.minutos_abierto)}
      </td>
    </tr>
  );
}

function TarjetaMovil({ t, equipo }: { t: TicketResumen; equipo: Carga[] }) {
  return (
    <li className={cx("border-t border-slate-100 px-4 py-4", t.estado === "ABIERTO" && "bg-orange-50/40")}>
      <div className="flex items-center justify-between gap-2">
        <Link to={`/tickets/${t.numero}`} className="font-mono text-sm font-semibold text-primario">{t.numero}</Link>
        <ChipEstado estado={t.estado} verificado={t.cierre_verificado} />
      </div>
      <Link to={`/tickets/${t.numero}`} className="mt-1 block font-semibold">{t.titulo}</Link>
      <div className="mt-2 flex items-end justify-between gap-3">
        <BarraVacio valor={t.estado === "CERRADO" ? t.pct_apertura : t.porcentaje_vacio} hasta={t.estado === "CERRADO" ? t.pct_cierre : null} umbral={t.umbral_vacio} />
        <Prioridad valor={t.prioridad} />
      </div>
      {t.producto_faltante && t.enriquecido_ia && <div className="mt-2"><ChipIA>IA: {t.producto_faltante}</ChipIA></div>}
      <div className="mt-3 flex items-center justify-between text-sm text-slate-600">
        <span>{t.estado === "CERRADO" ? `cerrado ${hora(t.cerrado_en)}` : `hace ${duracion(t.minutos_abierto)}`}</span>
        {t.estado === "ABIERTO" && equipo.length ? <SelectorAsignar ticket={t} equipo={equipo} onListo={() => undefined} /> : <span>{t.asignado_nombre ?? "Sin asignar"}</span>}
      </div>
    </li>
  );
}

function EquipoTurno({ equipo }: { equipo: Carga[] }) {
  const maximo = Math.max(3, ...equipo.map((u) => u.asignados + u.en_progreso));
  return (
    <section className="tarjeta p-5">
      <div className="mb-4 flex items-baseline justify-between">
        <h2 className="text-lg font-bold">Equipo de turno</h2>
        <span className="text-xs text-slate-500">{equipo.length} reponedores</span>
      </div>
      <ul className="flex flex-col gap-4">
        {equipo.map((u) => {
          const activos = u.asignados + u.en_progreso;
          return (
            <li key={u.usuario_id} className="flex items-center gap-3">
              <Avatar nombre={u.reponedor} tamano="sm" />
              <div className="min-w-0 flex-1">
                <div className="flex items-baseline justify-between gap-2 text-sm">
                  <span className="truncate font-semibold">{u.reponedor}</span>
                  <span className={cx("shrink-0 text-xs", activos ? "text-slate-600" : "text-green-700")}>
                    {activos ? `${activos} activo${activos > 1 ? "s" : ""}` : `libre${u.cerrados_hoy ? ` · ${u.cerrados_hoy} cerrado${u.cerrados_hoy > 1 ? "s" : ""}` : ""}`}
                  </span>
                </div>
                <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-slate-100">
                  <div className="h-full rounded-full bg-primario" style={{ width: `${(activos / maximo) * 100}%` }} />
                </div>
              </div>
            </li>
          );
        })}
        {!equipo.length && <li className="text-sm text-slate-500">Sin reponedores en este recinto.</li>}
      </ul>
    </section>
  );
}

function UltimasAlertas({ alertas }: { alertas: Alerta[] }) {
  return (
    <section className="tarjeta p-5">
      <h2 className="mb-4 text-lg font-bold">Últimas alertas</h2>
      <ul className="flex flex-col gap-3">
        {alertas.map((a) => (
          <li key={`${a.numero}-${a.en}`} className="flex gap-3 text-sm">
            <span className="w-11 shrink-0 text-slate-500 tabular-nums">{hora(a.en)}</span>
            <Link to={`/tickets/${a.numero}`} className="hover:underline">
              {a.tipo === "SEGUIMIENTO" && a.anterior !== null ? (
                <>
                  {a.categoria ?? a.gondola_codigo} {Number(a.porcentaje_vacio) > Number(a.anterior) ? "subió" : "bajó"} de {pct(a.anterior)} a{" "}
                  <b className="text-vacio">{pct(a.porcentaje_vacio)}</b> · seguimiento en {a.numero}
                </>
              ) : (
                <>
                  <b className="text-vacio">{pct(a.porcentaje_vacio)}</b> en {a.gondola_codigo} · {a.categoria} · abrió {a.numero}
                </>
              )}
            </Link>
          </li>
        ))}
        {!alertas.length && <li className="text-sm text-slate-500">Sin alertas en las últimas 48 h.</li>}
      </ul>
    </section>
  );
}

export function Bandeja() {
  const { usuario, recintoId } = useSesion();
  const recinto = useRecinto();
  const [vista, setVista] = useState<Vista>("todos");
  const [prioridad, setPrioridad] = useState<TPrioridad | "">("");
  const [busqueda, setBusqueda] = useState("");
  const [q, setQ] = useState("");
  const esReponedor = usuario?.rol === "REPONEDOR";

  useEffect(() => {
    const t = setTimeout(() => setQ(busqueda.trim()), 300);
    return () => clearTimeout(t);
  }, [busqueda]);

  const { data, isLoading } = useQuery({
    queryKey: ["tickets", recintoId, vista, prioridad, q],
    queryFn: () => api<TBandeja>("/tickets", { consulta: { recinto_id: recintoId, vista, prioridad, q } }),
    enabled: Boolean(recintoId),
    refetchInterval: 60_000,
  });
  const { data: equipo = [] } = useQuery({
    queryKey: ["equipo", recintoId],
    queryFn: () => api<Carga[]>(`/recintos/${recintoId}/equipo`),
    enabled: Boolean(recintoId) && !esReponedor,
  });
  const { data: alertas = [] } = useQuery({
    queryKey: ["alertas", recintoId],
    queryFn: () => api<Alerta[]>(`/recintos/${recintoId}/alertas`, { consulta: { limite: 6 } }),
    enabled: Boolean(recintoId) && !esReponedor,
  });

  if (!recinto) return <EstadoVacio titulo="No tienes recintos asignados" detalle="Pide al administrador que te asigne uno." />;
  const c = data?.conteos;
  const enProgreso = data?.tickets.find((t) => t.estado === "EN_PROGRESO");
  const filtros: [Vista, string, number | undefined][] = [
    ["todos", "Todos", c?.todos],
    ["sin_asignar", "Sin asignar", c?.sin_asignar],
    ["asignados", "Asignados", c?.asignados],
    ["en_progreso", "En progreso", c?.en_progreso],
    ["cerrados_hoy", "Cerrados", c?.cerrados_hoy],
  ];

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold">{esReponedor ? "Mis tickets" : "Tickets del recinto"}</h1>
          <p className="mt-1 text-sm text-slate-600">
            {recinto.nombre} · se abren solos cuando una foto supera {pct(recinto.umbral_vacio, 0)} de vacío
          </p>
        </div>
        <div className="flex w-full flex-wrap items-center gap-3 sm:w-auto">
          <label className="relative min-w-0 flex-1 sm:w-72 sm:flex-none">
            <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-slate-400" aria-hidden />
            <input
              className="campo pl-9"
              placeholder="Buscar INC, góndola o producto"
              value={busqueda}
              onChange={(e) => setBusqueda(e.target.value)}
              aria-label="Buscar tickets"
            />
          </label>
          <Campana />
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Tarjeta titulo="Sin asignar" valor={c?.sin_asignar} destacada activa={vista === "sin_asignar"} onClick={() => setVista("sin_asignar")}
          detalle={c?.sin_asignar_mas_antiguo_min ? `El más antiguo hace ${duracion(c.sin_asignar_mas_antiguo_min)}` : "Nada pendiente"} />
        <Tarjeta titulo="Asignados" valor={c?.asignados} activa={vista === "asignados"} onClick={() => setVista("asignados")}
          detalle="Esperando que el reponedor parta" />
        <Tarjeta titulo="En progreso" valor={c?.en_progreso} activa={vista === "en_progreso"} onClick={() => setVista("en_progreso")}
          detalle={enProgreso ? `${enProgreso.asignado_nombre} · ${enProgreso.categoria ?? enProgreso.gondola_codigo ?? ""}` : "—"} />
        <Tarjeta titulo="Cerrados hoy" valor={c?.cerrados_hoy} activa={vista === "cerrados_hoy"} onClick={() => setVista("cerrados_hoy")}
          detalle={`${c?.cerrados_hoy_verificados ?? 0} con foto de verificación`} />
      </div>

      <div className="grid gap-6 xl:grid-cols-[1fr_18rem]">
        <section className="tarjeta min-w-0 overflow-hidden">
          <div className="flex flex-wrap items-center gap-2 border-b border-slate-100 px-4 py-3">
            {filtros.map(([v, nombre, n]) => (
              <button
                key={v}
                onClick={() => setVista(v)}
                className={cx(
                  "rounded-lg border px-3 py-1.5 text-sm font-medium transition",
                  vista === v ? "border-slate-900 bg-slate-900 text-white" : v === "sin_asignar" ? "border-orange-200 bg-marca-suave text-orange-800" : "border-slate-300 text-slate-700 hover:bg-slate-50",
                )}
              >
                {nombre} · {n ?? 0}
              </button>
            ))}
            <label className="ml-auto flex items-center gap-2 text-sm text-slate-600">
              Prioridad
              <select className="campo w-auto py-1.5" value={prioridad} onChange={(e) => setPrioridad(e.target.value as TPrioridad | "")}>
                <option value="">Todas</option>
                <option value="CRITICA">Crítica</option>
                <option value="ALTA">Alta</option>
                <option value="MEDIA">Media</option>
                <option value="BAJA">Baja</option>
              </select>
            </label>
          </div>
          {isLoading ? (
            <Cargando />
          ) : data?.tickets.length ? (
            <>
            <ul className="md:hidden">
              {data.tickets.map((t) => <TarjetaMovil key={t.id} t={t} equipo={equipo} />)}
            </ul>
            <div className="hidden overflow-x-auto md:block">
              <table className="w-full min-w-[760px]">
                <thead>
                  <tr>
                    <th className="tabla-cabecera">Ticket</th>
                    <th className="tabla-cabecera">Vacío</th>
                    <th className="tabla-cabecera">Prioridad</th>
                    <th className="tabla-cabecera">Estado</th>
                    <th className="tabla-cabecera">Asignado a</th>
                    <th className="tabla-cabecera">Abierto hace</th>
                  </tr>
                </thead>
                <tbody>
                  {data.tickets.map((t) => <Fila key={t.id} t={t} equipo={equipo} />)}
                </tbody>
              </table>
            </div>
            </>
          ) : (
            <EstadoVacio icono={<Inbox className="size-10" />} titulo={q ? "Sin resultados" : "No hay tickets en esta vista"}
              detalle={q ? "Prueba con el número INC, el código de la góndola o el producto." : "Los tickets se abren solos cuando una cámara detecta un vacío sobre el umbral."} />
          )}
        </section>
        {!esReponedor && (
          <aside className="flex flex-col gap-6">
            <EquipoTurno equipo={equipo} />
            <UltimasAlertas alertas={alertas} />
          </aside>
        )}
      </div>
    </div>
  );
}
