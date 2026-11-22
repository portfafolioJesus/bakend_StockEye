import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router";
import { Boton } from "../componentes/ui";
import { api } from "../lib/api";
import { useSesion } from "../lib/sesion";

export function CambiarClave() {
  const { usuario, refrescar } = useSesion();
  const [f, setF] = useState({ actual: "", nueva: "", repetir: "" });
  const [error, setError] = useState("");
  const [cargando, setCargando] = useState(false);
  const ir = useNavigate();

  const enviar = async (e: FormEvent) => {
    e.preventDefault();
    if (f.nueva !== f.repetir) return setError("Las claves nuevas no coinciden");
    setCargando(true);
    setError("");
    try {
      await api("/auth/clave", { cuerpo: { actual: f.actual, nueva: f.nueva } });
      await refrescar();
      ir(usuario?.rol === "ADMINISTRADOR" ? "/admin" : "/", { replace: true });
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setCargando(false);
    }
  };
  return (
    <div className="mx-auto max-w-md">
      <h1 className="mb-1 text-2xl font-bold">Cambia tu clave</h1>
      <p className="mb-6 text-sm text-slate-600">
        {usuario?.debe_cambiar_clave ? "Ingresaste con una clave temporal: define una propia para continuar." : "Mínimo 8 caracteres."}
      </p>
      <form onSubmit={enviar} className="tarjeta flex flex-col gap-4 p-6">
        {(["actual", "nueva", "repetir"] as const).map((k) => (
          <label key={k}>
            <span className="etiqueta">{k === "actual" ? "Clave actual" : k === "nueva" ? "Clave nueva" : "Repite la clave nueva"}</span>
            <input className="campo" type="password" required minLength={k === "actual" ? 1 : 8}
              autoComplete={k === "actual" ? "current-password" : "new-password"}
              value={f[k]} onChange={(e) => setF({ ...f, [k]: e.target.value })} />
          </label>
        ))}
        {error && <p className="text-sm text-red-700" role="alert">{error}</p>}
        <Boton type="submit" cargando={cargando}>Guardar clave</Boton>
      </form>
    </div>
  );
}
