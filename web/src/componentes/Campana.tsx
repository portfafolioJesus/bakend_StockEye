import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bell, BellRing } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router";
import { api } from "../lib/api";
import { hace } from "../lib/formato";
import { activarPush, estadoPush, type EstadoPush } from "../lib/tiempoReal";
import type { Notificacion } from "../lib/tipos";
import { useSesion } from "../lib/sesion";
import { cx, useAvisos } from "./ui";

export function Campana() {
  const [abierta, setAbierta] = useState(false);
  const [push, setPush] = useState<EstadoPush>("pendiente");
  const ref = useRef<HTMLDivElement>(null);
  const qc = useQueryClient();
  const ir = useNavigate();
  const { usuario, elegirRecinto } = useSesion();
  const avisar = useAvisos();
  const { data } = useQuery({
    queryKey: ["notificaciones"],
    queryFn: () => api<{ no_leidas: number; notificaciones: Notificacion[] }>("/notificaciones", { consulta: { limite: 15 } }),
    refetchInterval: 10_000,
  });
  const leer = useMutation({
    mutationFn: (id?: number) =>
      id ? api(`/notificaciones/${id}`, { metodo: "PATCH", cuerpo: { leida: true } }) : api("/notificaciones/leer-todas", { metodo: "POST" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["notificaciones"] }),
  });

  useEffect(() => {
    estadoPush().then(setPush).catch(() => setPush("no_soportado"));
  }, []);
  useEffect(() => {
    const fuera = (e: MouseEvent) => ref.current && !ref.current.contains(e.target as Node) && setAbierta(false);
    document.addEventListener("mousedown", fuera);
    return () => document.removeEventListener("mousedown", fuera);
  }, []);

  const pedirPush = async () => {
    try {
      const r = await activarPush();
      setPush(r);
      avisar(
        r === "activo" ? "Avisos del navegador activados" : r === "deshabilitado" ? "El servidor no tiene Web Push configurado" : "El navegador bloqueó las notificaciones",
        r === "activo" ? "ok" : "error",
      );
    } catch {
      avisar("No se pudieron activar los avisos", "error");
    }
  };

  const n = data?.no_leidas ?? 0;
  return (
    <div className="relative" ref={ref}>
      <button
        onClick={() => setAbierta((a) => !a)}
        className="relative flex size-10 items-center justify-center rounded-lg border border-slate-300 bg-white text-slate-700 hover:bg-slate-50"
        aria-label={`Notificaciones${n ? `, ${n} sin leer` : ""}`}
      >
        <Bell className="size-5" />
        {n > 0 && (
          <span className="absolute -top-1.5 -right-1.5 flex min-w-5 items-center justify-center rounded-full bg-marca px-1 text-[11px] font-bold text-white">
            {n > 99 ? "99+" : n}
          </span>
        )}
      </button>
      {abierta && (
        <div className="absolute right-0 z-30 mt-2 w-[min(24rem,calc(100vw-2rem))] overflow-hidden rounded-xl border border-slate-200 bg-white shadow-xl">
          <div className="flex items-center justify-between border-b border-slate-100 px-4 py-3">
            <span className="font-semibold">Notificaciones</span>
            {n > 0 && (
              <button className="text-sm font-medium text-primario" onClick={() => leer.mutate(undefined)}>
                Marcar todas como leídas
              </button>
            )}
          </div>
          {push === "pendiente" && (
            <button onClick={pedirPush} className="flex w-full items-center gap-2 bg-blue-50 px-4 py-2.5 text-left text-sm font-medium text-primario">
              <BellRing className="size-4" /> Recibir avisos aunque el panel esté cerrado
            </button>
          )}
          <ul className="max-h-96 overflow-y-auto">
            {(data?.notificaciones ?? []).map((x) => (
              <li key={x.id}>
                <button
                  className={cx("flex w-full flex-col gap-0.5 px-4 py-3 text-left hover:bg-slate-50", !x.leida && "bg-orange-50/60")}
                  onClick={() => {
                    if (!x.leida) leer.mutate(x.id);
                    if (x.tipo === "IA_CUOTA" && usuario?.rol !== "REPONEDOR") {
                      if (x.recinto_id && usuario?.recintos.some((r) => r.id === x.recinto_id)) elegirRecinto(x.recinto_id);
                      ir("/caracterizacion?estado=pendientes");
                    } else if (x.ticket_numero) ir(`/tickets/${x.ticket_numero}`);
                    setAbierta(false);
                  }}
                >
                  <span className="text-sm">{x.mensaje}</span>
                  <span className="text-xs text-slate-500">{hace(x.creada_en)}</span>
                </button>
              </li>
            ))}
            {!data?.notificaciones.length && <li className="px-4 py-8 text-center text-sm text-slate-500">Sin notificaciones</li>}
          </ul>
        </div>
      )}
    </div>
  );
}
