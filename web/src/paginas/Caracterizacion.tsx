import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ImageOff, RefreshCw, Sparkles } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router";
import { AvisoCaracterizacion } from "../componentes/AvisoCaracterizacion";
import { Campana } from "../componentes/Campana";
import { Boton, Cargando, cx, EstadoVacio, Modal, useAvisos } from "../componentes/ui";
import { api, ErrorApi } from "../lib/api";
import { fechaHora, num, pct } from "../lib/formato";
import { useRecinto, useSesion } from "../lib/sesion";
import type { BandejaCaracterizacion, EstadoCaracterizacion, ImagenCaracterizacion } from "../lib/tipos";

const NOMBRES: Record<EstadoCaracterizacion, string> = {
  NO_REQUERIDA: "Categoría de origen",
  PENDIENTE: "Pendiente",
  PROCESANDO: "Caracterizando",
  AUTOMATICA: "Automática",
  MANUAL: "Manual",
  REVISION: "Revisión manual",
};
const FILTROS = [
  ["", "Todas las imágenes"], ["pendientes", "Pendientes de caracterización"], ["REVISION", "En revisión manual"],
  ["AUTOMATICA", "Caracterizadas por IA"], ["MANUAL", "Caracterizadas manualmente"], ["NO_REQUERIDA", "Categoría de origen"],
];
const LIMITE = 100;

function Miniatura({ url, id }: { url: string | null; id: number }) {
  const [fuente, setFuente] = useState(url);
  const [fallo, setFallo] = useState(false);
  useEffect(() => {
    if ((!fuente || fallo) && url && fuente !== url) { setFuente(url); setFallo(false); }
  }, [url, fuente, fallo]);
  if (!fuente || fallo) return <div className="flex h-48 items-center justify-center gap-2 bg-slate-100 text-sm text-slate-500"><ImageOff className="size-5" /> Fotografía no disponible</div>;
  return <a href={url ?? fuente} target="_blank" rel="noreferrer" aria-label={`Abrir fotografía ${id}`}><img src={fuente} alt={`Fotografía ${id} de la góndola`} loading="lazy" className="h-48 w-full bg-slate-100 object-contain" onError={() => setFallo(true)} /></a>;
}

export function Caracterizacion() {
  const { recintoId } = useSesion();
  const recinto = useRecinto();
  const [parametros, setParametros] = useSearchParams();
  const estadoSolicitado = parametros.get("estado") ?? "";
  const estado = FILTROS.some(([valor]) => valor === estadoSolicitado) ? estadoSolicitado : "";
  const [offset, setOffset] = useState(0);
  const [edicion, setEdicion] = useState<ImagenCaracterizacion | null>(null);
  const [categoria, setCategoria] = useState("");
  const [producto, setProducto] = useState("");
  const [errorFormulario, setErrorFormulario] = useState<string | null>(null);
  const [conflicto, setConflicto] = useState(false);
  const qc = useQueryClient();
  const avisar = useAvisos();
  useEffect(() => { setOffset(0); setEdicion(null); }, [recintoId, estado]);
  const { data, isLoading, isError, error, isFetching, refetch } = useQuery({
    queryKey: ["caracterizaciones", recintoId, estado, offset],
    queryFn: () => api<BandejaCaracterizacion>("/caracterizaciones", { consulta: { recinto_id: recintoId, estado, limite: LIMITE, offset } }),
    enabled: Boolean(recintoId),
    refetchInterval: 10_000,
  });
  const guardar = useMutation({
    mutationFn: () => {
      if (!edicion || !categoria) throw new Error("Selecciona una categoría.");
      return api(`/caracterizaciones/${edicion.id}`, { metodo: "PATCH", cuerpo: { categoria_id: Number(categoria), producto: producto.trim() || null, version: edicion.version_caracterizacion } });
    },
    onSuccess: () => {
      setEdicion(null);
      avisar("Caracterización manual guardada", "ok");
      for (const clave of ["caracterizaciones", "caracterizaciones-resumen", "tickets", "ticket", "notificaciones"]) qc.invalidateQueries({ queryKey: [clave] });
    },
    onError: (e) => {
      const desactualizada = e instanceof ErrorApi && e.status === 409;
      setConflicto(desactualizada);
      setErrorFormulario(desactualizada ? "Esta imagen cambió mientras la editabas. Actualiza la lista y vuelve a abrirla para revisar la versión actual." : e instanceof Error ? e.message : "No se pudo guardar la caracterización.");
    },
  });
  const abrir = (imagen: ImagenCaracterizacion) => {
    setEdicion(imagen); setCategoria(imagen.categoria_id ? String(imagen.categoria_id) : "");
    setProducto(imagen.producto_caracterizado ?? ""); setErrorFormulario(null); setConflicto(false);
  };
  if (!recinto) return <EstadoVacio titulo="Elige un recinto" />;
  const imagenes = data?.imagenes ?? [];
  const total = data?.total;
  const haySiguiente = total === undefined ? imagenes.length === LIMITE : offset + imagenes.length < total;
  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold">Caracterización de imágenes</h1>
          <p className="mt-1 text-sm text-slate-600">{recinto.nombre} · todas las fotografías, incluidas las que no generan ticket.</p>
        </div>
        <div className="flex items-center gap-3"><Boton variante="secundario" onClick={() => refetch()} disabled={isFetching}><RefreshCw className={cx("size-4", isFetching && "animate-spin")} /> Actualizar</Boton><Campana /></div>
      </div>
      {!!data?.incidencias.length && <AvisoCaracterizacion incidencias={data.incidencias} pendientes={data.pendientes} />}
      <section className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-slate-200 bg-white p-4">
        <p className="text-sm"><strong className="text-lg tabular-nums">{data?.pendientes ?? "—"}</strong> pendientes de caracterización en este recinto</p>
        <label className="flex items-center gap-2 text-sm font-medium">Mostrar<select className="campo w-auto" value={estado} onChange={(e) => setParametros(e.target.value ? { estado: e.target.value } : {})}>{FILTROS.map(([valor, nombre]) => <option key={valor} value={valor}>{nombre}</option>)}</select></label>
      </section>
      {isLoading ? <Cargando texto="Cargando fotografías…" /> : isError ? <div role="alert" className="rounded-xl border border-red-200 bg-red-50 p-4 text-red-800">{error instanceof Error ? error.message : "No se pudieron cargar las fotografías."}</div> : !imagenes.length ? <EstadoVacio icono={<Sparkles className="size-10" />} titulo={estado ? "No hay imágenes en esta vista" : "Todavía no hay imágenes"} detalle={`Las nuevas fotos entran por entradas/${recinto.codigo}/por_clasificar.`} /> : (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {imagenes.map((imagen) => <article key={`${recintoId}-${imagen.id}`} className="overflow-hidden rounded-xl border border-slate-200 bg-white">
            <Miniatura url={imagen.url_original} id={imagen.id} />
            <div className="flex flex-col gap-3 p-4">
              <div className="flex items-center justify-between gap-2"><h2 className="font-semibold">Imagen #{imagen.id}</h2><span className={cx("rounded-full px-2 py-1 text-xs font-semibold", imagen.estado_caracterizacion === "MANUAL" || imagen.estado_caracterizacion === "AUTOMATICA" ? "bg-green-50 text-green-800" : "bg-amber-50 text-amber-900")}>{NOMBRES[imagen.estado_caracterizacion] ?? imagen.estado_caracterizacion}</span></div>
              <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-sm"><dt className="text-slate-500">Vacío</dt><dd className="font-semibold">{num(imagen.porcentaje_vacio) === null ? "Sin medición" : pct(imagen.porcentaje_vacio)} <span className="font-normal text-slate-500">{imagen.estado === "ERROR" ? "· error de análisis" : imagen.estado !== "PROCESADA" ? "· análisis pendiente" : ""}</span></dd><dt className="text-slate-500">Categoría</dt><dd>{imagen.categoria ?? "Pendiente de identificar"}</dd><dt className="text-slate-500">Producto</dt><dd>{imagen.producto_caracterizado ?? "Sin identificar"}</dd><dt className="text-slate-500">Recibida</dt><dd>{fechaHora(imagen.recibida_en)}</dd></dl>
              <div className="mt-auto flex flex-wrap items-center justify-between gap-2">{imagen.ticket_numero ? <Link to={`/tickets/${imagen.ticket_numero}`} className="text-sm font-semibold text-primario">Ver {imagen.ticket_numero}</Link> : <span className="text-xs text-slate-500">Sin ticket</span>}<Boton variante="secundario" tamano="sm" onClick={() => abrir(imagen)}>{imagen.estado_caracterizacion === "MANUAL" || imagen.estado_caracterizacion === "AUTOMATICA" || imagen.estado_caracterizacion === "NO_REQUERIDA" ? "Revisar / corregir" : "Caracterizar manualmente"}</Boton></div>
            </div>
          </article>)}
        </div>
      )}
      {!isLoading && !!imagenes.length && <div className="flex flex-wrap items-center justify-between gap-3 text-sm text-slate-600"><span>Mostrando {offset + 1}–{offset + imagenes.length}{total !== undefined ? ` de ${total}` : ""}</span><div className="flex gap-2"><Boton variante="secundario" tamano="sm" disabled={offset === 0 || isFetching} onClick={() => setOffset(Math.max(0, offset - LIMITE))}>Anterior</Boton><Boton variante="secundario" tamano="sm" disabled={!haySiguiente || isFetching} onClick={() => setOffset(offset + LIMITE)}>Siguiente</Boton></div></div>}
      <Modal abierto={Boolean(edicion)} titulo={`Caracterizar imagen #${edicion?.id ?? ""}`} onCerrar={() => { if (!guardar.isPending) setEdicion(null); }}>
        {edicion && <form className="flex flex-col gap-4" onSubmit={(e) => { e.preventDefault(); guardar.mutate(); }}>
          <Miniatura key={edicion.id} url={edicion.url_original} id={edicion.id} />
          <p className="text-sm text-slate-600">Vacío: {num(edicion.porcentaje_vacio) === null ? "Sin medición" : pct(edicion.porcentaje_vacio)}. La corrección se registrará como una decisión manual.</p>
          <label className="text-sm font-medium">Categoría<select required className="campo mt-1" value={categoria} onChange={(e) => setCategoria(e.target.value)} disabled={guardar.isPending || conflicto}><option value="">Seleccionar categoría</option>{data?.categorias.map((c) => <option key={c.id} value={c.id}>{c.nombre}</option>)}</select></label>
          <label className="text-sm font-medium">Producto o descripción <span className="font-normal text-slate-500">(opcional)</span><input className="campo mt-1" value={producto} onChange={(e) => setProducto(e.target.value)} maxLength={150} placeholder="Déjalo vacío si no puedes identificarlo" disabled={guardar.isPending || conflicto} /></label>
          {errorFormulario && <p role="alert" className="text-sm text-red-700">{errorFormulario}</p>}
          <div className="flex justify-end gap-2"><Boton type="button" variante="secundario" disabled={guardar.isPending} onClick={() => { setEdicion(null); if (conflicto) refetch(); }}>{conflicto ? "Actualizar lista" : "Cancelar"}</Boton><Boton type="submit" cargando={guardar.isPending} disabled={!categoria || conflicto}>Guardar caracterización</Boton></div>
        </form>}
      </Modal>
    </div>
  );
}
