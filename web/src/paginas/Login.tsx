import { useState, type FormEvent } from "react";
import { Navigate, useNavigate } from "react-router";
import { Boton } from "../componentes/ui";
import { useSesion } from "../lib/sesion";

export function Login() {
  const { usuario, ingresar } = useSesion();
  const [email, setEmail] = useState("");
  const [clave, setClave] = useState("");
  const [error, setError] = useState("");
  const [cargando, setCargando] = useState(false);
  const ir = useNavigate();
  if (usuario) return <Navigate to={usuario.debe_cambiar_clave ? "/clave" : usuario.rol === "ADMINISTRADOR" ? "/admin" : "/"} replace />;

  const enviar = async (e: FormEvent) => {
    e.preventDefault();
    setError("");
    setCargando(true);
    try {
      const u = await ingresar(email, clave);
      ir(u.debe_cambiar_clave ? "/clave" : u.rol === "ADMINISTRADOR" ? "/admin" : "/", { replace: true });
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setCargando(false);
    }
  };

  return (
    <div className="flex min-h-dvh items-center justify-center bg-lateral p-4">
      <form onSubmit={enviar} className="w-full max-w-sm rounded-2xl bg-white p-8 shadow-2xl">
        <div className="mb-6 flex items-center gap-3">
          <img src="/icono.svg" alt="" className="size-9" />
          <div>
            <p className="font-display text-2xl font-bold">StockEye</p>
            <p className="text-sm text-slate-500">Vacíos en góndola, resueltos a tiempo</p>
          </div>
        </div>
        <label className="mb-4 block">
          <span className="etiqueta">Email</span>
          <input className="campo" type="email" autoComplete="username" required autoFocus value={email} onChange={(e) => setEmail(e.target.value)} />
        </label>
        <label className="mb-2 block">
          <span className="etiqueta">Clave</span>
          <input className="campo" type="password" autoComplete="current-password" required value={clave} onChange={(e) => setClave(e.target.value)} />
        </label>
        {error && <p className="mb-2 text-sm text-red-700" role="alert">{error}</p>}
        <Boton type="submit" className="mt-4 w-full" cargando={cargando}>Ingresar</Boton>
        <p className="mt-6 text-center text-xs text-slate-500">Reponedores: usen la app StockEye en el celular.</p>
      </form>
    </div>
  );
}
