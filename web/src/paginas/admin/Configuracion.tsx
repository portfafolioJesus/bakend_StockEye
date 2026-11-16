import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Copy, KeyRound, Plus, Upload } from "lucide-react";
import { useEffect, useState, type FormEvent, type ReactNode } from "react";
import { useLocation } from "react-router";
import { Diagnostico } from "../../componentes/Diagnostico";
import { Boton, Cargando, cx, Modal, Seccion, useAvisos } from "../../componentes/ui";
import { api } from "../../lib/api";
import { fechaHora, hace, hora, NOMBRE_ROL, num } from "../../lib/formato";
import type { Camara, Categoria, Gondola, Rol } from "../../lib/tipos";
import { EstadoCamara } from "../Gondolas";

interface RecintoAdmin {
  id: number; codigo: string; nombre: string; carpeta_imagenes: string; umbral_vacio: string; activo: boolean;
  supervisores: number; reponedores: number; camaras: number; camaras_en_linea: number;
}
interface UsuarioAdmin {
  id: number; nombre: string; apellido: string; email: string; rol: Rol; activo: boolean; ultimo_acceso: string | null;
  ultimo_acceso_origen: string | null; recintos: string[]; recinto_ids: number[]; debe_cambiar_clave: boolean;
}
interface ModeloAdmin {
  id: number; nombre: string; version: string; familia: string; ruta_pesos: string; umbral_confianza: string;
  clases: Record<string, string>; metricas: Record<string, number>; parametros: Record<string, number | string>;
  activo: boolean; cargado_en: string; activado_en: string | null; activado_por_nombre: string | null;
  predicciones: number; inferencia_ms_promedio: number | null; archivo_presente: boolean;
}
interface IAConfig {
  activo: boolean; proveedor: string; modelo: string; recortar_a_gondola: boolean; api_key_configurada: boolean;
  proveedores: string[]; uso_7_dias: { analisis: number; fallidos: number; latencia_ms: number | null };
  modelo_forzado_por_entorno: string | null;
}
interface Cola {
  recintos: { recinto: string; pendientes: number; procesando: number; errores_24h: number; p95_espera_s: string | null }[];
  workers: { worker: string; imagenes_ultima_hora: number; ultima: string }[];
}

const ESTILO_ROL: Record<Rol, string> = {
  ADMINISTRADOR: "bg-orange-100 text-orange-800", SUPERVISOR: "bg-indigo-50 text-indigo-700", REPONEDOR: "bg-slate-100 text-slate-700",
};

function Secreto({ titulo, valor, aviso }: { titulo: string; valor: string; aviso: string }) {
  const avisar = useAvisos();
  return (
    <div className="flex flex-col gap-3">
      <p className="text-sm text-slate-600">{aviso}</p>
      <div className="flex items-center gap-2 rounded-lg bg-slate-900 p-3 font-mono text-sm text-white">
        <KeyRound className="size-4 shrink-0 text-orange-300" aria-hidden />
        <span className="flex-1 break-all select-all" aria-label={titulo}>{valor}</span>
        <button className="rounded p-1 hover:bg-white/10" aria-label="Copiar"
          onClick={() => navigator.clipboard?.writeText(valor).then(() => avisar("Copiado"))}>
          <Copy className="size-4" />
        </button>
      </div>
    </div>
  );
}

function useCampos<T extends Record<string, unknown>>(inicial: T) {
  const [f, setF] = useState(inicial);
  const campo = (k: keyof T) => ({
    value: f[k] as string,
    onChange: (e: { target: { value: string } }) => setF((x) => ({ ...x, [k]: e.target.value })),
  });
  return { f, setF, campo, reiniciar: () => setF(inicial) };
}

// ---------------------------------------------------------------- recintos

function TarjetaRecinto({ r }: { r: RecintoAdmin }) {
  const [umbral, setUmbral] = useState(String(num(r.umbral_vacio)));
  const qc = useQueryClient();
  const avisar = useAvisos();
  const guardar = useMutation({
    mutationFn: () => api(`/admin/recintos/${r.id}`, { metodo: "PATCH", cuerpo: { umbral_vacio: Number(umbral) } }),
    onSuccess: () => {
      avisar(`Umbral de ${r.codigo}: ${umbral} %. Aplica a las fotos nuevas.`);
      qc.invalidateQueries({ queryKey: ["admin", "recintos"] });
    },
    onError: (e: Error) => avisar(e.message, "error"),
  });
  const todas = r.camaras_en_linea === r.camaras;
  return (
    <div className="tarjeta p-5">
      <div className="flex items-start justify-between gap-3">
        <p className="text-sm font-semibold text-slate-600">{r.codigo}</p>
        <span className={cx("rounded-full px-2.5 py-0.5 text-xs font-semibold", todas ? "bg-green-50 text-green-700" : "bg-orange-50 text-orange-800")}>
          {r.camaras_en_linea} de {r.camaras} cámaras en línea
        </span>
      </div>
      <h3 className="text-xl font-bold">{r.nombre}</h3>
      <p className="font-mono text-sm text-slate-500">{r.carpeta_imagenes}</p>
      <div className="mt-4 flex flex-wrap items-end justify-between gap-3">
        <label>
          <span className="etiqueta">Umbral de alerta</span>
          <span className="flex items-center gap-2 text-sm text-slate-600">
            <input type="number" min={0} max={100} step={0.5} className="campo w-20" value={umbral}
              onChange={(e) => setUmbral(e.target.value)}
              onBlur={() => Number(umbral) !== num(r.umbral_vacio) && guardar.mutate()}
              onKeyDown={(e) => e.key === "Enter" && (e.target as HTMLInputElement).blur()} />
            % de vacío
          </span>
        </label>
        <p className="text-sm text-slate-600">{r.supervisores} supervisor{r.supervisores === 1 ? "" : "es"} · {r.reponedores} reponedores</p>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------- cámaras

function NuevaCamara({ abierto, onCerrar, recintos }: { abierto: boolean; onCerrar: () => void; recintos: RecintoAdmin[] }) {
  const { f, campo, reiniciar } = useCampos({ recinto_id: "", gondola_id: "", codigo: "", nombre: "", url_stream: "", intervalo: "300" });
  const [clave, setClave] = useState<string | null>(null);
  const qc = useQueryClient();
  const avisar = useAvisos();
  const { data: gondolas = [] } = useQuery({
    queryKey: ["admin", "gondolas", f.recinto_id],
    queryFn: () => api<Gondola[]>("/admin/gondolas", { consulta: { recinto_id: f.recinto_id } }),
    enabled: Boolean(f.recinto_id),
  });
  const crear = useMutation({
    mutationFn: () => api<{ api_key: string }>("/admin/camaras", {
      cuerpo: { recinto_id: Number(f.recinto_id), gondola_id: f.gondola_id ? Number(f.gondola_id) : null, codigo: f.codigo.toUpperCase(),
        nombre: f.nombre || null, url_stream: f.url_stream || null, intervalo_captura_seg: Number(f.intervalo) },
    }),
    onSuccess: (r) => {
      setClave(r.api_key);
      qc.invalidateQueries({ queryKey: ["admin"] });
    },
    onError: (e: Error) => avisar(e.message, "error"),
  });
  const cerrar = () => {
    setClave(null);
    reiniciar();
    onCerrar();
  };
  const recinto = recintos.find((r) => String(r.id) === f.recinto_id);
  return (
    <Modal abierto={abierto} titulo={clave ? "Cámara creada" : "Agregar cámara"} onCerrar={cerrar}>
      {clave ? (
        <div className="flex flex-col gap-4">
          <Secreto titulo="API key" valor={clave} aviso="Copia esta API key en el capturador del recinto (camaras.json). No se volverá a mostrar: en la base de datos solo queda su hash." />
          <Boton onClick={cerrar}>Listo</Boton>
        </div>
      ) : (
        <form className="flex flex-col gap-4" onSubmit={(e: FormEvent) => { e.preventDefault(); crear.mutate(); }}>
          <div className="grid gap-4 sm:grid-cols-2">
            <label><span className="etiqueta">Recinto</span>
              <select className="campo" required {...campo("recinto_id")}>
                <option value="">Elige…</option>
                {recintos.map((r) => <option key={r.id} value={r.id}>{r.nombre}</option>)}
              </select>
            </label>
            <label><span className="etiqueta">Góndola que enfoca</span>
              <select className="campo" {...campo("gondola_id")} disabled={!f.recinto_id}>
                <option value="">Sin góndola</option>
                {gondolas.map((g) => <option key={g.id} value={g.id}>{g.codigo} · {g.categoria}</option>)}
              </select>
            </label>
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <label><span className="etiqueta">Código</span>
              <input className="campo uppercase" required pattern="[A-Za-z0-9-]{3,30}" placeholder={recinto ? `${recinto.codigo}-CAM09` : "R01-CAM09"} {...campo("codigo")} />
            </label>
            <label><span className="etiqueta">Frecuencia</span>
              <select className="campo" {...campo("intervalo")}>
                {[60, 120, 300, 600, 900].map((s) => <option key={s} value={s}>cada {s / 60} min</option>)}
              </select>
            </label>
          </div>
          <label><span className="etiqueta">URL RTSP o snapshot (sin usuario ni clave)</span>
            <input className="campo font-mono" placeholder="rtsp://192.168.1.20:554/Streaming/Channels/102" {...campo("url_stream")} />
            <span className="mt-1 block text-xs text-slate-500">El usuario de solo lectura y su clave van únicamente en el capturador del recinto.</span>
          </label>
          <div className="flex justify-end gap-3">
            <Boton type="button" variante="secundario" onClick={cerrar}>Cancelar</Boton>
            <Boton type="submit" cargando={crear.isPending}>Crear y generar API key</Boton>
          </div>
        </form>
      )}
    </Modal>
  );
}

function NuevoRecinto({ abierto, onCerrar }: { abierto: boolean; onCerrar: () => void }) {
  const { f, campo, reiniciar } = useCampos({ codigo: "", nombre: "", direccion: "", comuna: "", umbral_vacio: "5" });
  const qc = useQueryClient();
  const avisar = useAvisos();
  const crear = useMutation({
    mutationFn: () => api("/admin/recintos", { cuerpo: { ...f, codigo: f.codigo.toUpperCase(), umbral_vacio: Number(f.umbral_vacio) } }),
    onSuccess: () => {
      avisar(`Recinto ${f.codigo.toUpperCase()} creado. Sus fotos se guardan en recintos/${f.codigo.toUpperCase()}`);
      qc.invalidateQueries({ queryKey: ["admin"] });
      reiniciar();
      onCerrar();
    },
    onError: (e: Error) => avisar(e.message, "error"),
  });
  return (
    <Modal abierto={abierto} titulo="Agregar recinto" onCerrar={onCerrar}>
      <form className="flex flex-col gap-4" onSubmit={(e) => { e.preventDefault(); crear.mutate(); }}>
        <div className="grid gap-4 sm:grid-cols-3">
          <label><span className="etiqueta">Código</span><input className="campo uppercase" required pattern="[A-Za-z0-9-]{2,20}" placeholder="R03" {...campo("codigo")} /></label>
          <label className="sm:col-span-2"><span className="etiqueta">Nombre</span><input className="campo" required placeholder="Recinto 3 · Maipú" {...campo("nombre")} /></label>
        </div>
        <div className="grid gap-4 sm:grid-cols-3">
          <label className="sm:col-span-2"><span className="etiqueta">Dirección</span><input className="campo" {...campo("direccion")} /></label>
          <label><span className="etiqueta">Comuna</span><input className="campo" {...campo("comuna")} /></label>
        </div>
        <label><span className="etiqueta">Umbral de alerta (% de vacío)</span>
          <input type="number" min={0} max={100} step={0.5} className="campo w-28" {...campo("umbral_vacio")} />
        </label>
        <div className="flex justify-end gap-3">
          <Boton type="button" variante="secundario" onClick={onCerrar}>Cancelar</Boton>
          <Boton type="submit" cargando={crear.isPending}>Crear recinto</Boton>
        </div>
      </form>
    </Modal>
  );
}

function NuevaGondola({ abierto, onCerrar, recintos }: { abierto: boolean; onCerrar: () => void; recintos: RecintoAdmin[] }) {
  const { f, campo, reiniciar } = useCampos({ recinto_id: "", categoria_id: "", descripcion: "", codigo: "" });
  const qc = useQueryClient();
  const avisar = useAvisos();
  const { data: categorias = [] } = useQuery({ queryKey: ["categorias"], queryFn: () => api<Categoria[]>("/categorias"), enabled: abierto });
  const crear = useMutation({
    mutationFn: () => api("/admin/gondolas", {
      cuerpo: { recinto_id: Number(f.recinto_id), categoria_id: Number(f.categoria_id), descripcion: f.descripcion || null, codigo: f.codigo || null },
    }),
    onSuccess: () => {
      avisar("Punto fijo creado");
      qc.invalidateQueries({ queryKey: ["admin", "gondolas"] });
      reiniciar();
      onCerrar();
    },
    onError: (e: Error) => avisar(e.message, "error"),
  });
  return (
    <Modal abierto={abierto} titulo="Agregar punto fijo" onCerrar={onCerrar}>
      <form className="flex flex-col gap-4" onSubmit={(e) => { e.preventDefault(); crear.mutate(); }}>
        <p className="text-sm text-slate-600">
          Un punto fijo es un lugar que siempre se fotografía dentro de una categoría (por ejemplo, lo que mira una cámara).
          Las fotos de un punto fijo se suman como seguimiento al ticket activo. No es necesario para cargar fotos sueltas por categoría.
        </p>
        <div className="grid gap-4 sm:grid-cols-2">
          <label><span className="etiqueta">Recinto</span>
            <select className="campo" required {...campo("recinto_id")}>
              <option value="">Elige…</option>
              {recintos.map((r) => <option key={r.id} value={r.id}>{r.nombre}</option>)}
            </select>
          </label>
          <label><span className="etiqueta">Categoría</span>
            <select className="campo" required {...campo("categoria_id")}>
              <option value="">Elige…</option>
              {categorias.map((c) => <option key={c.id} value={c.id}>{c.nombre}</option>)}
            </select>
          </label>
        </div>
        <label><span className="etiqueta">Descripción del lugar</span><input className="campo" required placeholder="Ej.: Yogures, pasillo central" {...campo("descripcion")} /></label>
        <label><span className="etiqueta">Código (opcional)</span><input className="campo uppercase" placeholder="Se genera solo" {...campo("codigo")} /></label>
        <div className="flex justify-end gap-3">
          <Boton type="button" variante="secundario" onClick={onCerrar}>Cancelar</Boton>
          <Boton type="submit" cargando={crear.isPending}>Crear</Boton>
        </div>
      </form>
    </Modal>
  );
}

// ---------------------------------------------------------------- usuarios

function FormUsuario({ abierto, onCerrar, recintos, usuario }: {
  abierto: boolean; onCerrar: () => void; recintos: RecintoAdmin[]; usuario?: UsuarioAdmin | null;
}) {
  const vacio = { nombre: "", apellido: "", email: "", rol: "REPONEDOR" as Rol, recintos: [] as number[] };
  const [f, setF] = useState(vacio);
  const [temporal, setTemporal] = useState<string | null>(null);
  useEffect(() => {
    if (abierto) setF(usuario ? { nombre: usuario.nombre, apellido: usuario.apellido, email: usuario.email, rol: usuario.rol, recintos: usuario.recinto_ids } : vacio);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [abierto, usuario]);
  const qc = useQueryClient();
  const avisar = useAvisos();
  const guardar = useMutation({
    mutationFn: () => usuario
      ? api(`/admin/usuarios/${usuario.id}`, { metodo: "PATCH", cuerpo: { nombre: f.nombre, apellido: f.apellido, rol: f.rol, recintos: f.recintos } })
      : api<{ clave_temporal: string }>("/admin/usuarios", { cuerpo: f }),
    onSuccess: (r) => {
      qc.invalidateQueries({ queryKey: ["admin"] });
      if (!usuario && r && typeof r === "object" && "clave_temporal" in r) setTemporal((r as { clave_temporal: string }).clave_temporal);
      else {
        avisar("Usuario actualizado");
        onCerrar();
      }
    },
    onError: (e: Error) => avisar(e.message, "error"),
  });
  const cerrar = () => {
    setTemporal(null);
    onCerrar();
  };
  return (
    <Modal abierto={abierto} titulo={temporal ? "Usuario invitado" : usuario ? "Editar usuario" : "Invitar usuario"} onCerrar={cerrar}>
      {temporal ? (
        <div className="flex flex-col gap-4">
          <Secreto titulo="Clave temporal" valor={temporal} aviso={`Entrega esta clave temporal a ${f.nombre} junto con su email (${f.email}). Deberá cambiarla al ingresar.`} />
          <Boton onClick={cerrar}>Listo</Boton>
        </div>
      ) : (
        <form className="flex flex-col gap-4" onSubmit={(e) => { e.preventDefault(); guardar.mutate(); }}>
          <div className="grid gap-4 sm:grid-cols-2">
            <label><span className="etiqueta">Nombre</span><input className="campo" required value={f.nombre} onChange={(e) => setF({ ...f, nombre: e.target.value })} /></label>
            <label><span className="etiqueta">Apellido</span><input className="campo" required value={f.apellido} onChange={(e) => setF({ ...f, apellido: e.target.value })} /></label>
          </div>
          <label><span className="etiqueta">Email</span>
            <input className="campo" type="email" required disabled={Boolean(usuario)} value={f.email} onChange={(e) => setF({ ...f, email: e.target.value })} />
          </label>
          <label><span className="etiqueta">Rol</span>
            <select className="campo" value={f.rol} onChange={(e) => setF({ ...f, rol: e.target.value as Rol })}>
              {(["REPONEDOR", "SUPERVISOR", "ADMINISTRADOR"] as Rol[]).map((r) => <option key={r} value={r}>{NOMBRE_ROL[r]}</option>)}
            </select>
          </label>
          {f.rol !== "ADMINISTRADOR" && (
            <fieldset>
              <legend className="etiqueta">Recintos</legend>
              <div className="flex flex-wrap gap-3">
                {recintos.map((r) => (
                  <label key={r.id} className="flex items-center gap-2 text-sm">
                    <input type="checkbox" className="size-4 accent-primario" checked={f.recintos.includes(r.id)}
                      onChange={(e) => setF({ ...f, recintos: e.target.checked ? [...f.recintos, r.id] : f.recintos.filter((x) => x !== r.id) })} />
                    {r.nombre}
                  </label>
                ))}
              </div>
            </fieldset>
          )}
          <div className="flex justify-end gap-3">
            <Boton type="button" variante="secundario" onClick={cerrar}>Cancelar</Boton>
            <Boton type="submit" cargando={guardar.isPending}>{usuario ? "Guardar" : "Invitar"}</Boton>
          </div>
        </form>
      )}
    </Modal>
  );
}

// ---------------------------------------------------------------- modelo e IA

function PanelModelo() {
  const qc = useQueryClient();
  const avisar = useAvisos();
  const [subir, setSubir] = useState(false);
  const [archivos, setArchivos] = useState<{ onnx?: File; json?: File }>({});
  const { data: modelos = [], isLoading } = useQuery({ queryKey: ["admin", "modelos"], queryFn: () => api<ModeloAdmin[]>("/admin/modelos") });
  const activo = modelos.find((m) => m.activo);
  const [confianza, setConfianza] = useState("");
  useEffect(() => setConfianza(activo ? String(num(activo.umbral_confianza)) : ""), [activo]);
  const activar = useMutation({
    mutationFn: (id: number) => api(`/admin/modelos/${id}/activar`, { metodo: "POST" }),
    onSuccess: () => { avisar("Modelo activado: los workers lo cargan en segundos"); qc.invalidateQueries({ queryKey: ["admin", "modelos"] }); },
    onError: (e: Error) => avisar(e.message, "error"),
  });
  const umbral = useMutation({
    mutationFn: () => api(`/admin/modelos/${activo!.id}`, { metodo: "PATCH", cuerpo: { umbral_confianza: Number(confianza) } }),
    onSuccess: () => { avisar("Confianza mínima actualizada"); qc.invalidateQueries({ queryKey: ["admin", "modelos"] }); },
    onError: (e: Error) => avisar(e.message, "error"),
  });
  const cargar = useMutation({
    mutationFn: () => {
      const form = new FormData();
      form.append("archivo", archivos.onnx!);
      form.append("manifiesto", archivos.json!);
      return api<{ id: number }>("/admin/modelos", { form });
    },
    onSuccess: () => { avisar("Modelo subido. Actívalo cuando quieras."); setSubir(false); setArchivos({}); qc.invalidateQueries({ queryKey: ["admin", "modelos"] }); },
    onError: (e: Error) => avisar(e.message, "error"),
  });
  if (isLoading) return <Seccion titulo="Modelo de visión" id="modelo"><Cargando /></Seccion>;
  const metrica = activo?.familia === "YOLO"
    ? ["mAP50 (validación)", activo.metricas.map50]
    : ["IoU vacío (validación)", activo?.metricas.iou_vacio];
  return (
    <Seccion id="modelo" titulo="Modelo de visión" extra={activo && <span className="rounded-full bg-green-50 px-2.5 py-0.5 text-xs font-semibold text-green-700">Activo</span>}>
      <div className="flex flex-col gap-4 p-5">
        {activo ? (
          <>
            <div>
              <p className="font-display text-xl font-bold">{activo.nombre} {activo.version}</p>
              <p className="font-mono text-xs break-words text-slate-500">{activo.ruta_pesos}</p>
              <p className="text-xs text-slate-500">activado {fechaHora(activo.activado_en)}{activo.activado_por_nombre ? ` por ${activo.activado_por_nombre}` : ""}</p>
              {!activo.archivo_presente && <p className="mt-1 text-sm text-red-700">El archivo no está en el servidor: el worker no puede cargarlo.</p>}
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="rounded-xl bg-slate-50 p-3">
                <p className="text-xs text-slate-600">{metrica[0]}</p>
                <p className="font-display text-2xl font-bold">{metrica[1] !== undefined ? Number(metrica[1]).toLocaleString("es-CL", { maximumFractionDigits: 3 }) : "—"}</p>
              </div>
              <div className="rounded-xl bg-slate-50 p-3">
                <p className="text-xs text-slate-600">Clases</p>
                <p className="font-semibold">{Object.values(activo.clases ?? {}).join(" · ")}</p>
              </div>
            </div>
            <p className="text-xs text-slate-500">
              {activo.familia} · ONNX en CPU · {activo.parametros.pixeles_max ? `${Math.round(Number(activo.parametros.pixeles_max) / 1000)} mil px por foto` : ""}
              {activo.inferencia_ms_promedio ? ` · ${activo.inferencia_ms_promedio} ms promedio (24 h)` : ""}
            </p>
            <label>
              <span className="etiqueta">{activo.familia === "YOLO" ? "Confianza mínima de detección" : "Confianza mínima de píxel vacío"}</span>
              <span className="flex gap-2">
                <input type="number" min={0.05} max={0.95} step={0.05} className="campo w-28" value={confianza} onChange={(e) => setConfianza(e.target.value)} />
                {Number(confianza) !== num(activo.umbral_confianza) && <Boton tamano="sm" cargando={umbral.isPending} onClick={() => umbral.mutate()}>Aplicar</Boton>}
              </span>
            </label>
          </>
        ) : (
          <p className="text-sm text-red-700">No hay modelo activo: las fotos quedan en cola sin analizar.</p>
        )}
        <button onClick={() => setSubir(true)} className="flex items-center justify-center gap-2 rounded-xl border-2 border-dashed border-slate-300 py-3 text-sm font-semibold text-slate-700 hover:bg-slate-50">
          <Upload className="size-4" /> Subir nuevo modelo (.onnx)
        </button>
        {modelos.filter((m) => !m.activo).length > 0 && (
          <div className="border-t border-slate-100 pt-3">
            <p className="mb-2 text-xs font-semibold tracking-wide text-slate-500 uppercase">Versiones anteriores</p>
            {modelos.filter((m) => !m.activo).map((m) => (
              <div key={m.id} className="flex items-center justify-between gap-2 py-1.5 text-sm">
                <span>{m.nombre} {m.version}{m.metricas.iou_vacio ? ` · IoU ${m.metricas.iou_vacio}` : m.metricas.map50 ? ` · mAP50 ${m.metricas.map50}` : ""}</span>
                <Boton variante="secundario" tamano="sm" cargando={activar.isPending && activar.variables === m.id} onClick={() => activar.mutate(m.id)}>Volver a esta</Boton>
              </div>
            ))}
          </div>
        )}
      </div>
      <Modal abierto={subir} titulo="Subir modelo" onCerrar={() => setSubir(false)}>
        <form className="flex flex-col gap-4" onSubmit={(e) => { e.preventDefault(); cargar.mutate(); }}>
          <p className="text-sm text-slate-600">
            Convierte el <code>.pt</code> entrenado con <code>herramientas/empaquetar_modelo.py</code> en un PC de desarrollo: genera el <code>.onnx</code> y su manifiesto <code>.json</code> con el tiempo medido. El servidor no usa PyTorch (límite de 4 GB de RAM).
          </p>
          <label><span className="etiqueta">Modelo (.onnx)</span>
            <input type="file" accept=".onnx" required className="campo" onChange={(e) => setArchivos({ ...archivos, onnx: e.target.files?.[0] })} />
          </label>
          <label><span className="etiqueta">Manifiesto (.json)</span>
            <input type="file" accept=".json,application/json" required className="campo" onChange={(e) => setArchivos({ ...archivos, json: e.target.files?.[0] })} />
          </label>
          <div className="flex justify-end gap-3">
            <Boton type="button" variante="secundario" onClick={() => setSubir(false)}>Cancelar</Boton>
            <Boton type="submit" cargando={cargar.isPending}>Subir</Boton>
          </div>
        </form>
      </Modal>
    </Seccion>
  );
}

function PanelIA() {
  const qc = useQueryClient();
  const avisar = useAvisos();
  const { data: c } = useQuery({ queryKey: ["admin", "ia"], queryFn: () => api<IAConfig>("/admin/ia") });
  const [modelo, setModelo] = useState("");
  useEffect(() => setModelo(c?.modelo ?? ""), [c?.modelo]);
  const [prueba, setPrueba] = useState<{ ok: boolean; detalle: string; latencia_ms?: number } | null>(null);
  const guardar = useMutation({
    mutationFn: (cuerpo: Partial<IAConfig>) => api("/admin/ia", { metodo: "PATCH", cuerpo }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["admin", "ia"] }); setPrueba(null); },
    onError: (e: Error) => avisar(e.message, "error"),
  });
  const probar = useMutation({
    mutationFn: () => api<{ ok: boolean; detalle: string; latencia_ms?: number }>("/admin/ia/probar", { metodo: "POST" }),
    onSuccess: setPrueba,
    onError: (e: Error) => setPrueba({ ok: false, detalle: e.message }),
  });
  if (!c) return <Seccion titulo="Identificación de producto con IA" id="ia"><Cargando /></Seccion>;
  return (
    <Seccion id="ia" titulo="Identificación de producto con IA" extra={
      <label className="flex cursor-pointer items-center gap-2 text-sm font-medium">
        <input type="checkbox" className="size-4 accent-primario" checked={c.activo} onChange={(e) => guardar.mutate({ activo: e.target.checked })} />
        {c.activo ? "Activa" : "Apagada"}
      </label>
    }>
      <div className="flex flex-col gap-4 p-5">
        <p className="text-sm text-slate-600">Completa “producto faltante” en los tickets nuevos y en las fotos de la app.</p>
        <div className="grid gap-3 sm:grid-cols-2">
          <label><span className="etiqueta">Proveedor</span>
            <select className="campo" value={c.proveedor} onChange={(e) => guardar.mutate({ proveedor: e.target.value })}>
              {c.proveedores.map((p) => <option key={p} value={p}>{p === "groq" ? "Groq" : p === "openai" ? "OpenAI" : p}</option>)}
            </select>
          </label>
          <label><span className="etiqueta">Modelo con visión</span>
            <input className="campo font-mono text-xs" value={modelo} onChange={(e) => setModelo(e.target.value)}
              onBlur={() => modelo && modelo !== c.modelo && guardar.mutate({ modelo })} />
          </label>
        </div>
        {c.modelo_forzado_por_entorno && <p className="text-xs text-amber-800">IA_MODELO en el servidor fuerza: {c.modelo_forzado_por_entorno}</p>}
        <div className={cx("rounded-xl p-3", c.api_key_configurada ? "bg-slate-50" : "bg-amber-50")}>
          <p className="text-sm font-semibold">{c.api_key_configurada ? "API key guardada en el gestor de secretos" : "Falta la API key"}</p>
          <p className="text-xs text-slate-600">
            {c.api_key_configurada
              ? "Vive en las variables de entorno del servidor. Nunca se guarda en la base de datos ni se muestra."
              : `Define ${c.proveedor === "groq" ? "GROQ_API_KEY" : "OPENAI_API_KEY"} en el .env del servidor y reinicia los servicios api e ia.`}
          </p>
        </div>
        <label className="flex items-start gap-2 text-sm text-slate-600">
          <input type="checkbox" className="mt-0.5 size-4 accent-primario" checked={c.recortar_a_gondola} onChange={(e) => guardar.mutate({ recortar_a_gondola: e.target.checked })} />
          Antes de enviarla, la foto se recorta a la góndola (zona de la cámara) para no incluir clientes.
        </label>
        <Boton variante="secundario" cargando={probar.isPending} onClick={() => probar.mutate()}>Probar conexión</Boton>
        {prueba && (
          <p className={cx("text-sm", prueba.ok ? "text-green-700" : "text-red-700")} role="status">
            {prueba.detalle}{prueba.latencia_ms ? ` · ${prueba.latencia_ms} ms` : ""}
          </p>
        )}
        <p className="text-xs text-slate-500">Últimos 7 días: {c.uso_7_dias.analisis} análisis{c.uso_7_dias.fallidos ? `, ${c.uso_7_dias.fallidos} fallidos` : ""}{c.uso_7_dias.latencia_ms ? ` · ${c.uso_7_dias.latencia_ms} ms promedio` : ""}</p>
      </div>
    </Seccion>
  );
}

function PanelCola() {
  const { data } = useQuery({ queryKey: ["admin", "cola"], queryFn: () => api<Cola>("/admin/cola"), refetchInterval: 15_000 });
  if (!data) return null;
  return (
    <Seccion titulo="Cola de análisis">
      <div className="flex flex-col gap-3 p-5 text-sm">
        {data.recintos.map((r) => (
          <div key={r.recinto} className="flex items-center justify-between gap-2">
            <span className="font-semibold">{r.recinto}</span>
            <span className="text-slate-600">
              {r.pendientes} en cola · {r.procesando} analizando{r.errores_24h ? ` · ${r.errores_24h} con error` : ""}
              {r.p95_espera_s ? ` · p95 ${Number(r.p95_espera_s).toLocaleString("es-CL")} s` : ""}
            </span>
          </div>
        ))}
        <p className="border-t border-slate-100 pt-3 text-xs text-slate-500">
          Workers activos (última hora): {data.workers.length ? data.workers.map((w) => `${w.worker} (${w.imagenes_ultima_hora})`).join(", ") : "ninguno procesó fotos"}
        </p>
      </div>
    </Seccion>
  );
}

// ---------------------------------------------------------------- página

function Tabla({ cabeceras, children }: { cabeceras: string[]; children: ReactNode }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[600px]">
        <thead><tr>{cabeceras.map((c) => <th key={c} className="tabla-cabecera">{c}</th>)}</tr></thead>
        <tbody>{children}</tbody>
      </table>
    </div>
  );
}

export function Configuracion() {
  const { hash } = useLocation();
  const qc = useQueryClient();
  const avisar = useAvisos();
  const [modal, setModal] = useState<"camara" | "gondola" | "usuario" | "recinto" | null>(null);
  const [editando, setEditando] = useState<UsuarioAdmin | null>(null);
  const [diag, setDiag] = useState<number | null>(null);
  const [clave, setClave] = useState<{ email: string; clave_temporal: string } | null>(null);
  const { data: recintos = [] } = useQuery({ queryKey: ["admin", "recintos"], queryFn: () => api<RecintoAdmin[]>("/admin/recintos") });
  const { data: camaras = [] } = useQuery({ queryKey: ["admin", "camaras"], queryFn: () => api<Camara[]>("/admin/camaras"), refetchInterval: 60_000 });
  const { data: usuarios = [] } = useQuery({ queryKey: ["admin", "usuarios"], queryFn: () => api<UsuarioAdmin[]>("/admin/usuarios") });
  const { data: gondolas = [] } = useQuery({ queryKey: ["admin", "gondolas", "todas"], queryFn: () => api<(Gondola & { recinto_codigo: string })[]>("/admin/gondolas") });

  useEffect(() => {
    if (hash) document.getElementById(hash.slice(1))?.scrollIntoView({ behavior: "smooth" });
    else window.scrollTo({ top: 0 });
  }, [hash]);

  const estadoUsuario = useMutation({
    mutationFn: (u: UsuarioAdmin) => api(`/admin/usuarios/${u.id}`, { metodo: "PATCH", cuerpo: { activo: !u.activo } }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["admin", "usuarios"] }),
    onError: (e: Error) => avisar(e.message, "error"),
  });
  const restablecer = useMutation({
    mutationFn: (u: UsuarioAdmin) => api<{ email: string; clave_temporal: string }>(`/admin/usuarios/${u.id}/clave`, { metodo: "POST" }),
    onSuccess: setClave,
    onError: (e: Error) => avisar(e.message, "error"),
  });

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold">Configuración del sistema</h1>
          <p className="mt-1 text-sm text-slate-600">Recintos, cámaras, modelo de visión, integración de IA y usuarios</p>
        </div>
        <div className="flex flex-wrap gap-3">
          <Boton variante="secundario" onClick={() => setModal("recinto")}><Plus className="size-4" /> Agregar recinto</Boton>
          <Boton onClick={() => setModal("camara")}><Plus className="size-4" /> Agregar cámara</Boton>
        </div>
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        {recintos.map((r) => <TarjetaRecinto key={r.id} r={r} />)}
        {!recintos.length && (
          <div className="tarjeta p-6 text-sm text-slate-600 md:col-span-2">
            Aún no hay recintos. Empieza con <b>Agregar recinto</b>, luego sus góndolas, cámaras y usuarios.
          </div>
        )}
      </div>

      <div className="grid gap-6 xl:grid-cols-[1fr_22rem]">
        <div className="flex min-w-0 flex-col gap-6">
          <Seccion titulo={`Cámaras · ${camaras.length}`} extra={<span className="text-xs text-slate-500">Cada cámara se autentica con su propia API key</span>}>
            <Tabla cabeceras={["Código", "Góndola", "Estado", "Última foto", "Frecuencia"]}>
              {camaras.map((c) => (
                <tr key={c.id} className={cx("border-t border-slate-100", !c.en_linea && "bg-orange-50/50")}>
                  <td className="px-4 py-3 font-semibold whitespace-nowrap">{c.codigo}</td>
                  <td className="px-4 py-3 text-sm">{c.gondola_codigo ? `${c.gondola_codigo} · ${c.categoria}` : "—"}</td>
                  <td className="px-4 py-3 whitespace-nowrap"><EstadoCamara c={c} /></td>
                  <td className={cx("px-4 py-3 text-sm whitespace-nowrap", !c.en_linea && "text-vacio")}>{hora(c.ultima_captura)}{!c.en_linea && c.ultima_captura ? ` · ${hace(c.ultima_captura)}` : ""}</td>
                  <td className="px-4 py-3 text-sm">
                    {c.en_linea ? `cada ${Math.round(c.intervalo_captura_seg / 60)} min` : <Boton variante="secundario" tamano="sm" onClick={() => setDiag(c.id)}>Diagnosticar</Boton>}
                  </td>
                </tr>
              ))}
            </Tabla>
          </Seccion>

          <Seccion id="usuarios" titulo={`Usuarios · ${usuarios.length}`} extra={<Boton variante="contorno" tamano="sm" onClick={() => { setEditando(null); setModal("usuario"); }}>Invitar usuario</Boton>}>
            <Tabla cabeceras={["Nombre", "Rol", "Recinto", "Último acceso", ""]}>
              {usuarios.map((u) => (
                <tr key={u.id} className={cx("border-t border-slate-100", !u.activo && "opacity-50")}>
                  <td className="px-4 py-3">
                    <p className="font-semibold">{u.nombre} {u.apellido}</p>
                    <p className="text-xs text-slate-500">{u.email}{u.debe_cambiar_clave ? " · clave temporal" : ""}</p>
                  </td>
                  <td className="px-4 py-3"><span className={cx("rounded-full px-2.5 py-0.5 text-xs font-semibold whitespace-nowrap", ESTILO_ROL[u.rol])}>{NOMBRE_ROL[u.rol]}</span></td>
                  <td className="px-4 py-3 text-sm">{u.rol === "ADMINISTRADOR" ? "Todos" : u.recintos.join(", ") || "—"}</td>
                  <td className="px-4 py-3 text-sm whitespace-nowrap text-slate-600">{hace(u.ultimo_acceso)}{u.ultimo_acceso_origen === "app" ? " · app" : ""}</td>
                  <td className="px-4 py-3">
                    <div className="flex justify-end gap-3 text-sm font-medium whitespace-nowrap">
                      <button className="text-primario hover:underline" onClick={() => { setEditando(u); setModal("usuario"); }}>Editar</button>
                      <button className="text-primario hover:underline" title="Restablecer clave temporal" onClick={() => restablecer.mutate(u)}>Clave</button>
                      <button className={u.activo ? "text-red-700 hover:underline" : "text-green-700 hover:underline"} onClick={() => estadoUsuario.mutate(u)}>{u.activo ? "Desactivar" : "Activar"}</button>
                    </div>
                  </td>
                </tr>
              ))}
            </Tabla>
          </Seccion>

          <Seccion titulo={`Puntos fijos · ${gondolas.length}`} extra={<Boton variante="contorno" tamano="sm" onClick={() => setModal("gondola")}>Agregar punto fijo</Boton>}>
            <ul className="grid gap-px bg-slate-100 sm:grid-cols-2 lg:grid-cols-3">
              {gondolas.map((g) => (
                <li key={g.id} className="bg-white px-5 py-3 text-sm">
                  <span className="font-semibold">{g.recinto_codigo} · {g.codigo}</span>
                  <span className="text-slate-600"> · {g.categoria ?? "sin categoría"}</span>
                </li>
              ))}
            </ul>
          </Seccion>
        </div>
        <aside className="flex flex-col gap-6">
          <PanelModelo />
          <PanelIA />
          <PanelCola />
        </aside>
      </div>

      <NuevaCamara abierto={modal === "camara"} onCerrar={() => setModal(null)} recintos={recintos} />
      <NuevoRecinto abierto={modal === "recinto"} onCerrar={() => setModal(null)} />
      <NuevaGondola abierto={modal === "gondola"} onCerrar={() => setModal(null)} recintos={recintos} />
      <FormUsuario abierto={modal === "usuario"} onCerrar={() => setModal(null)} recintos={recintos} usuario={editando} />
      <Diagnostico camaraId={diag} onCerrar={() => setDiag(null)} />
      <Modal abierto={clave !== null} titulo="Clave restablecida" onCerrar={() => setClave(null)}>
        {clave && (
          <div className="flex flex-col gap-4">
            <Secreto titulo="Clave temporal" valor={clave.clave_temporal} aviso={`Entrega esta clave temporal a ${clave.email}. Deberá cambiarla al ingresar.`} />
            <Boton onClick={() => setClave(null)}>Listo</Boton>
          </div>
        )}
      </Modal>
    </div>
  );
}
