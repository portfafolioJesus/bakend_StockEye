import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Camera, Check, ImageOff } from "lucide-react";
import { useEffect, useState, type FormEvent } from "react";
import { Link, useParams } from "react-router";
import { Avatar, Boton, Cargando, ChipEstado, ChipIA, cx, EstadoVacio, Modal, Prioridad, useAvisos } from "../componentes/ui";
import { api, ErrorApi } from "../lib/api";
import { duracion, hora, NOMBRE_ESTADO, NOMBRE_PRIORIDAD, num, pct } from "../lib/formato";
import type { DetalleTicket as TDetalle, EstadoTicket, Evidencia } from "../lib/tipos";

const COLOR_EVENTO: Record<string, string> = {
  apertura: "bg-slate-400", asignacion: "bg-primario", estado: "bg-violet-500", seguimiento: "bg-marca", cierre: "bg-green-600", ia: "bg-ia",
};
const NOMBRE_EVIDENCIA = { APERTURA: "Apertura", SEGUIMIENTO: "Seguimiento", CIERRE: "Cierre" };

function Metrica({ titulo, valor, detalle, resaltada }: { titulo: string; valor: string; detalle?: string; resaltada?: boolean }) {
  return (
    <div className={cx("rounded-xl p-4", resaltada ? "bg-marca-suave" : "bg-slate-50")}>
      <p className={cx("text-sm", resaltada ? "text-orange-900" : "text-slate-600")}>{titulo}</p>
      <p className={cx("font-display mt-1 font-bold", valor.length > 8 ? "text-base leading-tight" : "text-3xl", resaltada && "text-vacio")}>{valor}</p>
      {detalle && <p className="mt-1 text-xs text-slate-500">{detalle}</p>}
    </div>
  );
}

function PanelEvidencia({ evidencias, umbral }: { evidencias: Evidencia[]; umbral: TDetalle["ticket"]["umbral_vacio"] }) {
  const [sel, setSel] = useState(evidencias.length - 1);
  useEffect(() => setSel(evidencias.length - 1), [evidencias.length]);
  const e = evidencias[sel];
  return (
    <section className="tarjeta p-5">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-lg font-bold">Evidencia</h2>
        {evidencias.length > 1 && (
          <div className="flex flex-wrap gap-1 rounded-xl bg-slate-100 p-1" role="tablist">
            {evidencias.map((x, i) => (
              <button
                key={x.imagen_id}
                role="tab"
                aria-selected={i === sel}
                onClick={() => setSel(i)}
                className={cx("rounded-lg px-3 py-1.5 text-sm", i === sel ? "bg-white font-semibold shadow-sm" : "text-slate-600")}
              >
                {NOMBRE_EVIDENCIA[x.tipo]} · {hora(x.capturada_en)} · {pct(x.porcentaje_vacio)}
              </button>
            ))}
          </div>
        )}
      </div>
      {e ? (
        <>
          <div className="overflow-hidden rounded-xl bg-slate-800">
            {e.url_anotada || e.url ? (
              <img src={e.url_anotada ?? e.url ?? ""} alt={`Foto ${NOMBRE_EVIDENCIA[e.tipo].toLowerCase()} de la góndola con los vacíos marcados`} className="mx-auto max-h-[460px] w-full object-contain" />
            ) : (
              <EstadoVacio icono={<ImageOff className="size-10" />} titulo="Imagen en análisis" />
            )}
          </div>
          <p className="mt-2 truncate text-xs text-slate-500">
            {e.ruta_archivo} · {e.url_anotada ? "imagen anotada por el modelo" : "original"}
            {e.subida_por_nombre && ` · tomada por ${e.subida_por_nombre}`}
          </p>
          <div className="mt-4 grid grid-cols-2 gap-3 lg:grid-cols-4">
            <Metrica titulo="Vacío detectado" valor={pct(e.porcentaje_vacio)} resaltada={Boolean(e.supera_umbral)} />
            <Metrica titulo="Umbral del recinto" valor={pct(e.umbral_aplicado ?? umbral, 0)} />
            <Metrica titulo="Espacios vacíos" valor={String(e.num_vacios ?? "—")} />
            <Metrica titulo="Modelo" valor={e.modelo ?? "—"} detalle={e.tiempo_inferencia_ms ? `inferencia ${e.tiempo_inferencia_ms} ms` : undefined} />
          </div>
        </>
      ) : (
        <EstadoVacio icono={<Camera className="size-10" />} titulo="Ticket sin fotos" detalle="Se creó de forma manual." />
      )}
    </section>
  );
}

function PanelAsignacion({ d, alGuardar }: { d: TDetalle; alGuardar: (id: number) => void }) {
  const [elegido, setElegido] = useState<number | null>(d.ticket.asignado_a);
  useEffect(() => setElegido(d.ticket.asignado_a), [d.ticket.asignado_a]);
  const nombre = d.equipo.find((u) => u.usuario_id === elegido)?.reponedor.split(" ")[0];
  return (
    <section className="tarjeta p-5">
      <h2 className="text-lg font-bold">Asignación</h2>
      <p className="mt-1 mb-3 text-sm text-slate-600">Reponedor responsable (solo de este recinto)</p>
      <div className="flex flex-col gap-2" role="radiogroup">
        {d.equipo.map((u) => {
          const activos = u.asignados + u.en_progreso;
          return (
            <button
              key={u.usuario_id}
              role="radio"
              aria-checked={elegido === u.usuario_id}
              disabled={!d.permisos.asignar}
              onClick={() => setElegido(u.usuario_id)}
              className={cx(
                "flex items-center justify-between rounded-xl border px-4 py-3 text-left transition disabled:cursor-default",
                elegido === u.usuario_id ? "border-2 border-primario bg-blue-50/50" : "border-slate-200 hover:bg-slate-50",
              )}
            >
              <span className="font-semibold">{u.reponedor}</span>
              <span className={cx("text-sm", activos ? "text-slate-500" : "font-semibold text-green-700")}>
                {activos ? `${activos} activo${activos > 1 ? "s" : ""}` : "libre"}
              </span>
            </button>
          );
        })}
      </div>
      {d.permisos.asignar && (
        <>
          <Boton className="mt-4 w-full" disabled={!elegido || elegido === d.ticket.asignado_a} onClick={() => elegido && alGuardar(elegido)}>
            Guardar asignación
          </Boton>
          {nombre && <p className="mt-2 text-xs text-slate-500">{nombre} recibirá una notificación push en la app.</p>}
        </>
      )}
    </section>
  );
}

function PanelDatos({ d, alGuardar, guardando }: { d: TDetalle; alGuardar: (c: Record<string, string>) => void; guardando: boolean }) {
  const t = d.ticket;
  const inicial = { producto_faltante: t.producto_faltante ?? "", categoria_producto: t.categoria_producto ?? t.categoria ?? "", descripcion: t.descripcion ?? "" };
  const [f, setF] = useState(inicial);
  useEffect(() => setF({ producto_faltante: t.producto_faltante ?? "", categoria_producto: t.categoria_producto ?? t.categoria ?? "", descripcion: t.descripcion ?? "" }),
    [t.producto_faltante, t.categoria_producto, t.categoria, t.descripcion]);
  const cambios = Object.fromEntries(Object.entries(f).filter(([k, v]) => v !== (inicial as Record<string, string>)[k]));
  const productos = d.ia?.exitoso ? d.ia.productos_faltantes : [];
  const [mejor, ...otros] = productos;
  return (
    <section className="tarjeta p-5">
      <h2 className="mb-4 text-lg font-bold">Datos del ticket</h2>
      <fieldset disabled={!d.permisos.editar} className="flex flex-col gap-4">
        <label>
          <span className="etiqueta">Producto faltante</span>
          <input className="campo" value={f.producto_faltante} onChange={(e) => setF({ ...f, producto_faltante: e.target.value })} placeholder="¿Qué producto falta?" />
          {mejor && (
            <button type="button" className="mt-1.5 text-left" onClick={() => setF({ ...f, producto_faltante: mejor.producto })}>
              <ChipIA>
                Sugerido por IA · {Math.round((mejor.confianza ?? 0) * 100)} %
                {f.producto_faltante !== mejor.producto && `: ${mejor.producto} (usar)`}
                {otros[0] && ` · otra opción: ${otros[0].producto} (${Math.round((otros[0].confianza ?? 0) * 100)} %)`}
              </ChipIA>
            </button>
          )}
          {!mejor && d.ia_pendiente && <p className="mt-1.5 text-xs text-ia">La IA está analizando la foto…</p>}
        </label>
        <label>
          <span className="etiqueta">Categoría</span>
          <input className="campo" value={f.categoria_producto} onChange={(e) => setF({ ...f, categoria_producto: e.target.value })} />
        </label>
        <label>
          <span className="etiqueta">Descripción</span>
          <textarea className="campo" rows={3} value={f.descripcion} onChange={(e) => setF({ ...f, descripcion: e.target.value })} />
        </label>
        {Object.keys(cambios).length > 0 && (
          <div className="flex justify-end gap-2">
            <Boton variante="secundario" tamano="sm" onClick={() => setF(inicial)}>Descartar</Boton>
            <Boton tamano="sm" cargando={guardando} onClick={() => alGuardar(cambios)}>Guardar cambios</Boton>
          </div>
        )}
      </fieldset>
    </section>
  );
}

function PanelComentarios({ d, numero }: { d: TDetalle; numero: string }) {
  const [texto, setTexto] = useState("");
  const qc = useQueryClient();
  const avisar = useAvisos();
  const enviar = useMutation({
    mutationFn: () => api(`/tickets/${numero}/comentarios`, { cuerpo: { texto } }),
    onSuccess: () => {
      setTexto("");
      qc.invalidateQueries({ queryKey: ["ticket", numero] });
    },
    onError: (e: Error) => avisar(e.message, "error"),
  });
  const alEnviar = (e: FormEvent) => {
    e.preventDefault();
    if (texto.trim()) enviar.mutate();
  };
  return (
    <section className="tarjeta p-5">
      <h2 className="mb-4 text-lg font-bold">Comentarios · {d.comentarios.length}</h2>
      <ul className="mb-4 flex flex-col gap-4">
        {d.comentarios.map((c) => (
          <li key={c.id} className="flex gap-3">
            <Avatar nombre={c.nombre} tamano="sm" oscuro={c.rol !== "REPONEDOR"} />
            <div className="min-w-0">
              <p className="text-sm"><b>{c.nombre}</b> <span className="text-slate-500">· {hora(c.creado_en)}</span></p>
              <p className="text-[15px] break-words whitespace-pre-line">{c.texto}</p>
            </div>
          </li>
        ))}
      </ul>
      {d.permisos.comentar && (
        <form onSubmit={alEnviar} className="flex gap-2">
          <input className="campo" value={texto} onChange={(e) => setTexto(e.target.value)} placeholder="Escribe un comentario" aria-label="Comentario" />
          <Boton type="submit" variante="secundario" cargando={enviar.isPending}>Enviar</Boton>
        </form>
      )}
    </section>
  );
}

export function DetalleTicket() {
  const { numero = "" } = useParams();
  const qc = useQueryClient();
  const avisar = useAvisos();
  const [motivo, setMotivo] = useState<{ estado: EstadoTicket; texto: string } | null>(null);
  const { data: d, isLoading, error } = useQuery({
    queryKey: ["ticket", numero],
    queryFn: () => api<TDetalle>(`/tickets/${numero}`),
  });
  const editar = useMutation({
    mutationFn: (cuerpo: Record<string, unknown>) => api<TDetalle>(`/tickets/${numero}`, { metodo: "PATCH", cuerpo }),
    onSuccess: (nuevo) => {
      qc.setQueryData(["ticket", numero], nuevo);
      qc.invalidateQueries({ queryKey: ["tickets"] });
      qc.invalidateQueries({ queryKey: ["equipo"] });
      setMotivo(null);
      avisar("Cambios guardados");
    },
    onError: (e: Error) => {
      // Cerrar sin foto verificada o cancelar piden un comentario
      if (e instanceof ErrorApi && e.status === 422 && motivo === null && editar.variables?.estado) {
        setMotivo({ estado: editar.variables.estado as EstadoTicket, texto: "" });
        avisar(e.message, "info");
      } else avisar(e.message, "error");
    },
  });

  if (isLoading) return <Cargando />;
  if (error || !d) return <EstadoVacio titulo="No se encontró el ticket" detalle={(error as Error)?.message} />;
  const t = d.ticket;
  const cambiarEstado = (estado: EstadoTicket) => {
    if (estado === "CANCELADO") setMotivo({ estado, texto: "" });
    else editar.mutate({ estado });
  };
  const origen = t.camara_tipo === "CARGA" ? "Foto cargada" : t.origen === "CAMARA" ? `Cámara ${t.camara_codigo}` : t.origen === "MOVIL" ? `Foto móvil · ${t.creado_por_nombre}` : `Manual · ${t.creado_por_nombre}`;

  return (
    <div className="flex flex-col gap-6">
      <nav className="text-sm text-slate-500" aria-label="Ruta">
        <Link to="/" className="font-medium text-primario hover:underline">Tickets</Link> / {t.numero}
      </nav>
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <h1 className="text-2xl font-bold sm:text-3xl">{t.titulo}</h1>
          <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-2 text-sm text-slate-600">
            <span className="rounded-md border border-slate-300 bg-white px-2 py-0.5 font-mono text-xs font-semibold text-slate-800">{t.numero}</span>
            <ChipEstado estado={t.estado} verificado={t.cierre_verificado} />
            <Prioridad valor={t.prioridad} conTexto={false} />
            <span>Prioridad {NOMBRE_PRIORIDAD[t.prioridad].toLowerCase()}</span>
            <span>· {origen} · abierto {hora(t.creado_en)}, hace {duracion(t.minutos_abierto)}</span>
          </div>
        </div>
        {d.permisos.cambiar_estado && (
          <div className="flex items-center gap-3">
            <label className="flex items-center gap-2 text-sm text-slate-600">
              Estado
              <select className="campo w-auto" value={t.estado} onChange={(e) => cambiarEstado(e.target.value as EstadoTicket)} disabled={editar.isPending}>
                {(["ABIERTO", "ASIGNADO", "EN_PROGRESO", "CERRADO", "CANCELADO"] as EstadoTicket[]).map((e) => (
                  <option key={e} value={e}>{NOMBRE_ESTADO[e]}</option>
                ))}
              </select>
            </label>
            {d.permisos.cancelar && <Boton variante="secundario" onClick={() => setMotivo({ estado: "CANCELADO", texto: "" })}>Cancelar ticket</Boton>}
          </div>
        )}
        {d.permisos.empezar && <Boton onClick={() => editar.mutate({ estado: "EN_PROGRESO" })}>Empezar</Boton>}
      </div>

      <div className="grid gap-6 xl:grid-cols-[1fr_22rem]">
        <div className="flex min-w-0 flex-col gap-6">
          <PanelEvidencia evidencias={d.evidencias} umbral={t.umbral_vacio} />
          <section className="tarjeta p-5">
            <h2 className="mb-4 text-lg font-bold">Historial</h2>
            <ol className="flex flex-col gap-3.5">
              {d.linea_tiempo.map((e, i) => (
                <li key={i} className="flex items-start gap-3 text-[15px]">
                  <span className="w-12 shrink-0 text-sm text-slate-500 tabular-nums">{hora(e.en)}</span>
                  <span className={cx("mt-2 size-2 shrink-0 rounded-full", COLOR_EVENTO[e.tipo] ?? "bg-slate-400")} aria-hidden />
                  <span>{e.texto}</span>
                </li>
              ))}
            </ol>
          </section>
        </div>
        <aside className="flex flex-col gap-6">
          {(d.permisos.asignar || t.asignado_a) && d.equipo.length > 0 && (
            <PanelAsignacion d={d} alGuardar={(id) => editar.mutate({ asignado_a: id })} />
          )}
          <PanelDatos d={d} guardando={editar.isPending} alGuardar={(c) => editar.mutate(c)} />
          <PanelComentarios d={d} numero={numero} />
          {t.estado === "CERRADO" && (
            <p className={cx("flex items-center gap-2 rounded-xl px-4 py-3 text-sm font-medium", t.cierre_verificado ? "bg-green-50 text-green-800" : "bg-amber-50 text-amber-900")}>
              <Check className="size-4" />
              {t.cierre_verificado ? `Cierre verificado con foto (${pct(t.pct_cierre)} de vacío)` : "Cerrado sin foto de verificación bajo el umbral"}
            </p>
          )}
        </aside>
      </div>

      <Modal abierto={motivo !== null} titulo={motivo?.estado === "CANCELADO" ? "Cancelar ticket" : `Cambiar a ${motivo ? NOMBRE_ESTADO[motivo.estado] : ""}`} onCerrar={() => setMotivo(null)}>
        <form
          className="flex flex-col gap-4"
          onSubmit={(e) => {
            e.preventDefault();
            if (motivo) editar.mutate({ estado: motivo.estado, comentario: motivo.texto });
          }}
        >
          <p className="text-sm text-slate-600">
            {motivo?.estado === "CANCELADO"
              ? "Indica el motivo. Queda en los comentarios del ticket."
              : `No hay una foto de cierre bajo el umbral (${pct(num(t.umbral_vacio), 0)}). Explica por qué se cierra sin verificación.`}
          </p>
          <textarea className="campo" rows={3} required minLength={5} autoFocus value={motivo?.texto ?? ""}
            onChange={(e) => motivo && setMotivo({ ...motivo, texto: e.target.value })} />
          <div className="flex justify-end gap-3">
            <Boton type="button" variante="secundario" onClick={() => setMotivo(null)}>Volver</Boton>
            <Boton type="submit" variante={motivo?.estado === "CANCELADO" ? "peligro" : "primario"} cargando={editar.isPending}>Confirmar</Boton>
          </div>
        </form>
      </Modal>
    </div>
  );
}
