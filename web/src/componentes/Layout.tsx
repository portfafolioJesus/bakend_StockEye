import { useQuery } from "@tanstack/react-query";
import { ChartColumn, Cpu, LayoutGrid, ListTodo, LogOut, Menu, Settings, Sparkles, Users, X } from "lucide-react";
import { useCallback, useState, type ReactNode } from "react";
import { NavLink, Outlet, useLocation } from "react-router";
import { api } from "../lib/api";
import { NOMBRE_ROL } from "../lib/formato";
import { useRecinto, useSesion } from "../lib/sesion";
import { useTiempoReal } from "../lib/tiempoReal";
import type { Bandeja, BandejaCaracterizacion } from "../lib/tipos";
import { AvisoCaracterizacion } from "./AvisoCaracterizacion";
import { Avatar, cx, useAvisos } from "./ui";

function Logo({ admin }: { admin?: boolean }) {
  return (
    <div className="flex items-center gap-2.5">
      <img src="/icono.svg" alt="" className="size-7" />
      <span className="font-display text-xl font-bold text-white">StockEye</span>
      {admin && <span className="rounded bg-orange-200 px-1.5 py-0.5 text-[10px] font-bold tracking-wide text-orange-900">ADMIN</span>}
    </div>
  );
}

function Enlace({ a, icono, children, insignia }: { a: string; icono: ReactNode; children: ReactNode; insignia?: number }) {
  const { pathname, hash } = useLocation();
  const [ruta, ancla] = a.split("#");
  return (
    <NavLink
      to={a}
      end
      className={() => {
        const activo = ancla ? pathname === ruta && hash === `#${ancla}` : pathname === ruta && !hash || (ruta !== "/" && ruta !== "/admin" && pathname.startsWith(ruta));
        return cx(
          "flex items-center gap-3 rounded-lg px-3 py-2.5 text-[15px] transition",
          activo ? "bg-lateral-2 font-semibold text-white" : "text-slate-300 hover:bg-white/5 hover:text-white",
        );
      }}
    >
      <span className="text-slate-300" aria-hidden>{icono}</span>
      <span className="flex-1">{children}</span>
      {!!insignia && <span className="rounded-full bg-marca px-2 py-0.5 text-xs font-bold text-white">{insignia}</span>}
    </NavLink>
  );
}

export function Layout() {
  const { usuario, salir, recintoId, elegirRecinto } = useSesion();
  const recinto = useRecinto();
  const ubicacion = useLocation();
  const [menu, setMenu] = useState(false);
  const avisar = useAvisos();
  const esAdmin = usuario?.rol === "ADMINISTRADOR";
  const alNotificar = useCallback((m: string) => avisar(m, "info"), [avisar]);
  useTiempoReal(Boolean(usuario), alNotificar);

  const { data: bandeja } = useQuery({
    queryKey: ["tickets", recintoId, "conteos"],
    queryFn: () => api<Bandeja>("/tickets", { consulta: { recinto_id: recintoId, limite: 1 } }),
    enabled: Boolean(recintoId) && usuario?.rol !== "REPONEDOR",
  });
  const { data: caracterizacion } = useQuery({
    queryKey: ["caracterizaciones-resumen", recintoId],
    queryFn: () => api<BandejaCaracterizacion>("/caracterizaciones", { consulta: { recinto_id: recintoId, limite: 1 } }),
    enabled: Boolean(recintoId) && Boolean(usuario) && usuario?.rol !== "REPONEDOR",
    refetchInterval: 10_000,
  });
  if (!usuario) return null;

  const lateral = (
    <div className="flex h-full flex-col gap-6 p-4">
      <div className="flex items-center justify-between px-2 pt-2">
        <Logo admin={esAdmin} />
        <button className="text-slate-300 lg:hidden" onClick={() => setMenu(false)} aria-label="Cerrar menú">
          <X className="size-6" />
        </button>
      </div>
      {usuario.recintos.length > 0 && (
        <label className="px-2">
          <span className="mb-1.5 block text-xs text-slate-400">Recinto</span>
          <select
            value={recintoId ?? ""}
            onChange={(e) => elegirRecinto(Number(e.target.value))}
            className="w-full rounded-lg border border-slate-600 bg-lateral-2 px-3 py-2 text-sm text-white focus:outline-none"
          >
            {usuario.recintos.map((r) => (
              <option key={r.id} value={r.id}>
                {r.nombre}
              </option>
            ))}
          </select>
        </label>
      )}
      <nav className="flex flex-col gap-1" onClick={() => setMenu(false)}>
        {esAdmin && (
          <>
            <Enlace a="/admin" icono={<Settings className="size-5" />}>Recintos y cámaras</Enlace>
            <Enlace a="/admin#usuarios" icono={<Users className="size-5" />}>Usuarios</Enlace>
            <Enlace a="/admin#modelo" icono={<Cpu className="size-5" />}>Modelo de visión</Enlace>
            <Enlace a="/admin#ia" icono={<Sparkles className="size-5" />}>Integración IA</Enlace>
            <div className="mx-3 my-2 border-t border-white/10" />
          </>
        )}
        <Enlace a="/" icono={<ListTodo className="size-5" />} insignia={bandeja?.conteos.sin_asignar}>Tickets</Enlace>
        {usuario.rol !== "REPONEDOR" && (
          <>
            <Enlace a="/caracterizacion" icono={<Sparkles className="size-5" />} insignia={caracterizacion?.pendientes}>Caracterización</Enlace>
            <Enlace a="/equipo" icono={<Users className="size-5" />}>Equipo</Enlace>
            <Enlace a="/gondolas" icono={<LayoutGrid className="size-5" />}>Góndolas y cámaras</Enlace>
            <Enlace a="/reportes" icono={<ChartColumn className="size-5" />}>Reportes</Enlace>
          </>
        )}
      </nav>
      <div className="mt-auto flex items-center gap-3 border-t border-white/10 px-2 pt-4">
        <Avatar nombre={`${usuario.nombre} ${usuario.apellido}`} oscuro />
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-semibold text-white">{usuario.nombre} {usuario.apellido}</p>
          <p className="truncate text-xs text-slate-400">
            {NOMBRE_ROL[usuario.rol]}
            {recinto && !esAdmin ? ` · ${recinto.codigo}` : ""}
          </p>
        </div>
        <button onClick={salir} className="rounded-lg p-2 text-slate-400 hover:bg-white/5 hover:text-white" aria-label="Cerrar sesión" title="Cerrar sesión">
          <LogOut className="size-4" />
        </button>
      </div>
    </div>
  );

  return (
    <div className="min-h-dvh lg:pl-64">
      <aside className="fixed inset-y-0 left-0 z-20 hidden w-64 bg-lateral lg:block">{lateral}</aside>
      {menu && (
        <div className="fixed inset-0 z-40 lg:hidden">
          <div className="absolute inset-0 bg-slate-900/60" onClick={() => setMenu(false)} />
          <aside className="absolute inset-y-0 left-0 w-72 bg-lateral">{lateral}</aside>
        </div>
      )}
      <header className="sticky top-0 z-10 flex items-center gap-3 bg-lateral px-4 py-3 lg:hidden">
        <button className="text-white" onClick={() => setMenu(true)} aria-label="Abrir menú">
          <Menu className="size-6" />
        </button>
        <Logo admin={esAdmin} />
      </header>
      <main className="mx-auto max-w-[1400px] px-4 py-6 sm:px-6 lg:px-8 lg:py-8">
        {usuario.rol !== "REPONEDOR" && ubicacion.pathname !== "/caracterizacion" && !!caracterizacion?.incidencias.length && (
          <div className="mb-6"><AvisoCaracterizacion incidencias={caracterizacion.incidencias} pendientes={caracterizacion.pendientes} /></div>
        )}
        <Outlet />
      </main>
    </div>
  );
}
