import "@fontsource-variable/inter";
import "@fontsource/space-grotesk/500.css";
import "@fontsource/space-grotesk/700.css";
import "./index.css";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode, type ReactNode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Navigate, Route, Routes } from "react-router";
import { Layout } from "./componentes/Layout";
import { Cargando, ProveedorAvisos } from "./componentes/ui";
import { ErrorApi } from "./lib/api";
import { ProveedorSesion, useSesion } from "./lib/sesion";
import type { Rol } from "./lib/tipos";
import { Configuracion } from "./paginas/admin/Configuracion";
import { Bandeja } from "./paginas/Bandeja";
import { CambiarClave } from "./paginas/CambiarClave";
import { Caracterizacion } from "./paginas/Caracterizacion";
import { DetalleTicket } from "./paginas/DetalleTicket";
import { Equipo } from "./paginas/Equipo";
import { Gondolas } from "./paginas/Gondolas";
import { Login } from "./paginas/Login";
import { Reportes } from "./paginas/Reportes";

const qc = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 15_000,
      retry: (n, e) => !(e instanceof ErrorApi && e.status >= 400 && e.status < 500) && n < 2,
      refetchOnWindowFocus: true,
    },
  },
});

function Protegida({ children, roles }: { children: ReactNode; roles?: Rol[] }) {
  const { usuario, cargando } = useSesion();
  if (cargando) return <Cargando texto="Abriendo sesión…" />;
  if (!usuario) return <Navigate to="/ingresar" replace />;
  if (roles && !roles.includes(usuario.rol)) return <Navigate to="/" replace />;
  return children;
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={qc}>
      <ProveedorAvisos>
        <ProveedorSesion>
          <BrowserRouter>
            <Routes>
              <Route path="/ingresar" element={<Login />} />
              <Route element={<Protegida><Layout /></Protegida>}>
                <Route index element={<Bandeja />} />
                <Route path="tickets/:numero" element={<DetalleTicket />} />
                <Route path="caracterizacion" element={<Protegida roles={["SUPERVISOR", "ADMINISTRADOR"]}><Caracterizacion /></Protegida>} />
                <Route path="equipo" element={<Protegida roles={["SUPERVISOR", "ADMINISTRADOR"]}><Equipo /></Protegida>} />
                <Route path="gondolas" element={<Protegida roles={["SUPERVISOR", "ADMINISTRADOR"]}><Gondolas /></Protegida>} />
                <Route path="reportes" element={<Protegida roles={["SUPERVISOR", "ADMINISTRADOR"]}><Reportes /></Protegida>} />
                <Route path="admin" element={<Protegida roles={["ADMINISTRADOR"]}><Configuracion /></Protegida>} />
                <Route path="clave" element={<CambiarClave />} />
                <Route path="*" element={<Navigate to="/" replace />} />
              </Route>
            </Routes>
          </BrowserRouter>
        </ProveedorSesion>
      </ProveedorAvisos>
    </QueryClientProvider>
  </StrictMode>,
);
