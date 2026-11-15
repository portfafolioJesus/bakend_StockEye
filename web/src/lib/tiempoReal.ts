// Tiempo real: SSE desde la api (que escucha LISTEN/NOTIFY de PostgreSQL)
// y suscripción Web Push para avisar con el navegador cerrado.
import { useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";
import { api, sesion } from "./api";

export function useTiempoReal(activo: boolean, alNotificar?: (mensaje: string, numero?: string) => void) {
  const qc = useQueryClient();
  useEffect(() => {
    if (!activo) return;
    let fuente: EventSource | null = null;
    let cerrado = false;
    let espera = 1000;
    let temporizador: number | undefined;

    const conectar = () => {
      const token = sesion.tokens()?.acceso;
      if (!token || cerrado) return;
      fuente = new EventSource(`/api/v1/eventos?token=${encodeURIComponent(token)}`);
      fuente.onopen = () => (espera = 1000);
      fuente.addEventListener("ticket", (e) => {
        const d = JSON.parse((e as MessageEvent).data);
        qc.invalidateQueries({ queryKey: ["tickets"] });
        qc.invalidateQueries({ queryKey: ["ticket", d.numero] });
        qc.invalidateQueries({ queryKey: ["equipo"] });
        qc.invalidateQueries({ queryKey: ["alertas"] });
      });
      fuente.addEventListener("notificacion", (e) => {
        const d = JSON.parse((e as MessageEvent).data);
        qc.invalidateQueries({ queryKey: ["notificaciones"] });
        alNotificar?.(d.mensaje, d.numero);
      });
      fuente.onerror = () => {
        // Token vencido o red caída: se reconecta con el token renovado y espera creciente.
        fuente?.close();
        if (cerrado) return;
        temporizador = window.setTimeout(async () => {
          await api("/auth/yo").catch(() => undefined);
          conectar();
        }, espera);
        espera = Math.min(espera * 2, 30000);
      };
    };
    conectar();
    return () => {
      cerrado = true;
      window.clearTimeout(temporizador);
      fuente?.close();
    };
  }, [activo, qc, alNotificar]);
}

function base64AUint8(base64: string): Uint8Array<ArrayBuffer> {
  const relleno = "=".repeat((4 - (base64.length % 4)) % 4);
  const crudo = atob((base64 + relleno).replace(/-/g, "+").replace(/_/g, "/"));
  const salida = new Uint8Array(new ArrayBuffer(crudo.length));
  for (let i = 0; i < crudo.length; i++) salida[i] = crudo.charCodeAt(i);
  return salida;
}

export type EstadoPush = "no_soportado" | "deshabilitado" | "denegado" | "activo" | "pendiente";

export async function estadoPush(): Promise<EstadoPush> {
  if (!("serviceWorker" in navigator) || !("PushManager" in window) || !("Notification" in window)) return "no_soportado";
  if (Notification.permission === "denied") return "denegado";
  const reg = await navigator.serviceWorker.getRegistration("/sw.js");
  const sub = await reg?.pushManager.getSubscription();
  return sub ? "activo" : "pendiente";
}

/** Pide permiso y registra el navegador en el notificador (Web Push / VAPID). */
export async function activarPush(): Promise<EstadoPush> {
  const estado = await estadoPush();
  if (estado === "no_soportado" || estado === "denegado") return estado;
  const { clave_publica, habilitado } = await api<{ clave_publica: string | null; habilitado: boolean }>("/webpush/clave");
  if (!habilitado || !clave_publica) return "deshabilitado";
  if ((await Notification.requestPermission()) !== "granted") return "denegado";
  const reg = await navigator.serviceWorker.register("/sw.js");
  await navigator.serviceWorker.ready;
  const sub =
    (await reg.pushManager.getSubscription()) ??
    (await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: base64AUint8(clave_publica) }));
  const json = sub.toJSON();
  await api("/webpush/suscripciones", { cuerpo: { endpoint: json.endpoint, keys: json.keys } });
  return "activo";
}
