import { useQueryClient } from "@tanstack/react-query";
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { api, sesion } from "./api";
import type { Usuario } from "./tipos";

interface Contexto {
  usuario: Usuario | null;
  cargando: boolean;
  recintoId: number | null;
  elegirRecinto: (id: number) => void;
  ingresar: (email: string, clave: string) => Promise<Usuario>;
  salir: () => void;
  refrescar: () => Promise<void>;
}

const Ctx = createContext<Contexto | null>(null);
const CLAVE_RECINTO = "stockeye.recinto";

function recintoGuardado(): number | null {
  try {
    const v = localStorage.getItem(CLAVE_RECINTO);
    return v ? Number(v) : null;
  } catch {
    return null;
  }
}

export function ProveedorSesion({ children }: { children: ReactNode }) {
  const [usuario, setUsuario] = useState<Usuario | null>(null);
  const [cargando, setCargando] = useState(Boolean(sesion.tokens()));
  const [recintoId, setRecintoId] = useState<number | null>(recintoGuardado());
  const qc = useQueryClient();

  const aplicar = useCallback((u: Usuario) => {
    setUsuario(u);
    setRecintoId((actual) => (u.recintos.some((r) => r.id === actual) ? actual : (u.recintos[0]?.id ?? null)));
  }, []);

  const refrescar = useCallback(async () => {
    aplicar(await api<Usuario>("/auth/yo"));
  }, [aplicar]);

  useEffect(() => {
    if (!sesion.tokens()) return;
    refrescar()
      .catch(() => sesion.cerrar())
      .finally(() => setCargando(false));
  }, [refrescar]);

  useEffect(
    () =>
      sesion.alExpirar(() => {
        setUsuario(null);
        qc.clear();
      }),
    [qc],
  );

  const valor = useMemo<Contexto>(
    () => ({
      usuario,
      cargando,
      recintoId,
      elegirRecinto(id) {
        setRecintoId(id);
        try {
          localStorage.setItem(CLAVE_RECINTO, String(id));
        } catch {
          /* sin almacenamiento */
        }
      },
      async ingresar(email, clave) {
        const r = await api<{ acceso: string; refresco: string; usuario: Usuario }>("/auth/login", {
          cuerpo: { email, clave, origen: "web" },
        });
        sesion.guardar({ acceso: r.acceso, refresco: r.refresco });
        aplicar(r.usuario);
        return r.usuario;
      },
      salir: () => sesion.cerrar(),
      refrescar,
    }),
    [usuario, cargando, recintoId, aplicar, refrescar],
  );
  return <Ctx.Provider value={valor}>{children}</Ctx.Provider>;
}

export function useSesion() {
  const c = useContext(Ctx);
  if (!c) throw new Error("useSesion fuera de ProveedorSesion");
  return c;
}

/** Recinto activo del selector lateral (con su umbral, nombre y carpeta). */
export function useRecinto() {
  const { usuario, recintoId } = useSesion();
  return usuario?.recintos.find((r) => r.id === recintoId) ?? null;
}
