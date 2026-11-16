import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ImagePlus, LoaderCircle } from "lucide-react";
import { useEffect, useRef, useState, type DragEvent } from "react";
import { Link } from "react-router";
import { api } from "../lib/api";
import { pct } from "../lib/formato";
import type { Categoria } from "../lib/tipos";
import { Boton, cx, Modal, useAvisos } from "./ui";

interface ImagenEstado {
  id: number;
  estado: "PENDIENTE" | "PROCESANDO" | "PROCESADA" | "ERROR";
  error: string | null;
  url_anotada: string | null;
  prediccion: { porcentaje_vacio: number; umbral_aplicado: number; supera_umbral: boolean; num_vacios: number; tiempo_inferencia_ms: number } | null;
  ticket: { numero: string; tipo: string } | null;
}
interface Fila {
  archivo: string;
  imagenId?: number;
  error?: string;
  imagen?: ImagenEstado;
}

const TIPOS = "image/jpeg,image/png,image/webp";

/** Sube fotos reales de una góndola. Se tratan como fotos de cámara: si superan
 *  el umbral abren un ticket solas (y las siguientes quedan como seguimiento). */
export function SubirFotos({ abierto, onCerrar, recintoId, carpeta }: {
  abierto: boolean; onCerrar: () => void; recintoId: number; carpeta: string;
}) {
  const [categoriaId, setCategoriaId] = useState("");
  const [puntoId, setPuntoId] = useState("");
  const [archivos, setArchivos] = useState<File[]>([]);
  const [filas, setFilas] = useState<Fila[]>([]);
  const [subiendo, setSubiendo] = useState(false);
  const [sobre, setSobre] = useState(false);
  const entrada = useRef<HTMLInputElement>(null);
  const qc = useQueryClient();
  const avisar = useAvisos();
  const { data: categorias = [] } = useQuery({
    queryKey: ["categorias", recintoId],
    queryFn: () => api<Categoria[]>(`/recintos/${recintoId}/categorias`),
    enabled: abierto,
  });
  const categoria = categorias.find((c) => String(c.id) === categoriaId);

  // Consulta el resultado del modelo hasta que todas las fotos estén analizadas
  const pendientes = filas.filter((f) => f.imagenId && (!f.imagen || ["PENDIENTE", "PROCESANDO"].includes(f.imagen.estado)));
  useEffect(() => {
    if (!pendientes.length) return;
    const t = setTimeout(async () => {
      const nuevas = await Promise.all(
        filas.map(async (f) =>
          f.imagenId && (!f.imagen || ["PENDIENTE", "PROCESANDO"].includes(f.imagen.estado))
            ? { ...f, imagen: await api<ImagenEstado>(`/imagenes/${f.imagenId}`).catch(() => f.imagen) }
            : f,
        ),
      );
      setFilas(nuevas);
      if (nuevas.some((f) => f.imagen?.ticket)) qc.invalidateQueries({ queryKey: ["tickets"] });
    }, 1000);
    return () => clearTimeout(t);
  }, [filas, pendientes.length, qc]);

  const agregar = (lista: FileList | null) => {
    if (!lista) return;
    const validos = Array.from(lista).filter((f) => TIPOS.split(",").includes(f.type));
    if (validos.length < lista.length) avisar("Algunos archivos no son JPEG, PNG ni WEBP y se omitieron", "info");
    setArchivos((a) => [...a, ...validos].slice(0, 50));
  };
  const soltar = (e: DragEvent) => {
    e.preventDefault();
    setSobre(false);
    agregar(e.dataTransfer.files);
  };
  // Una foto por petición: cada una puede pesar hasta 15 MB y se ve el avance
  const subir = async () => {
    if (!categoriaId || !archivos.length) return;
    setSubiendo(true);
    const lista = archivos;
    setArchivos([]);
    setFilas(lista.map((f) => ({ archivo: f.name })));
    for (const [i, archivo] of lista.entries()) {
      const form = new FormData();
      form.append(puntoId ? "gondola_id" : "categoria_id", puntoId || categoriaId);
      form.append("recinto_id", String(recintoId));
      form.append("fotos", archivo);
      let fila: Fila;
      try {
        const r = await api<{ resultados: { archivo: string; imagen_id?: number; error?: string }[] }>("/imagenes/carga", { form });
        const x = r.resultados[0];
        fila = { archivo: archivo.name, imagenId: x?.imagen_id, error: x?.error };
      } catch (e) {
        fila = { archivo: archivo.name, error: (e as Error).message };
      }
      setFilas((actual) => actual.map((f, j) => (j === i ? fila : f)));
    }
    setSubiendo(false);
  };
  const cerrar = () => {
    setArchivos([]);
    setFilas([]);
    onCerrar();
  };

  return (
    <Modal abierto={abierto} titulo="Subir fotos de góndola" onCerrar={cerrar} ancho="max-w-2xl">
      <div className="flex flex-col gap-4">
        <p className="text-sm text-slate-600">
          Se analizan con el modelo como si vinieran de una cámara: si una foto supera el umbral se abre un ticket sin asignar
          para el supervisor. Mientras ese ticket esté activo, las siguientes de la categoría se suman como seguimiento.
        </p>
        <div className="grid gap-4 sm:grid-cols-2">
          <label>
            <span className="etiqueta">Categoría</span>
            <select className="campo" value={categoriaId} onChange={(e) => { setCategoriaId(e.target.value); setPuntoId(""); }}>
              <option value="">Elige la categoría de las fotos…</option>
              {categorias.map((c) => <option key={c.id} value={c.id}>{c.departamento} · {c.nombre}</option>)}
            </select>
          </label>
          <label>
            <span className="etiqueta">Punto fijo (opcional)</span>
            <select className="campo" value={puntoId} onChange={(e) => setPuntoId(e.target.value)} disabled={!categoria?.puntos?.length}>
              <option value="">Ninguno: cada foto es un reporte</option>
              {categoria?.puntos?.map((g) => <option key={g.id} value={g.id}>{g.descripcion ?? g.codigo}</option>)}
            </select>
          </label>
        </div>
        <button
          type="button"
          onClick={() => entrada.current?.click()}
          onDragOver={(e) => { e.preventDefault(); setSobre(true); }}
          onDragLeave={() => setSobre(false)}
          onDrop={soltar}
          className={cx(
            "flex flex-col items-center gap-2 rounded-xl border-2 border-dashed px-4 py-8 text-sm transition",
            sobre ? "border-primario bg-blue-50" : "border-slate-300 hover:bg-slate-50",
          )}
        >
          <ImagePlus className="size-8 text-slate-400" aria-hidden />
          <span className="font-semibold text-slate-700">Arrastra las fotos aquí o haz clic para elegirlas</span>
          <span className="text-slate-500">JPEG, PNG o WEBP · hasta 50 fotos de 15 MB</span>
        </button>
        <input ref={entrada} type="file" accept={TIPOS} multiple hidden onChange={(e) => { agregar(e.target.files); e.target.value = ""; }} />
        {archivos.length > 0 && (
          <p className="text-sm text-slate-700">{archivos.length} foto{archivos.length > 1 ? "s" : ""} lista{archivos.length > 1 ? "s" : ""}: {archivos.map((f) => f.name).join(", ")}</p>
        )}
        {filas.length > 0 && (
          <ul className="divide-y divide-slate-100 rounded-xl border border-slate-200">
            {filas.map((f, i) => {
              const p = f.imagen?.prediccion;
              const enCurso = !f.error && (!f.imagen || ["PENDIENTE", "PROCESANDO"].includes(f.imagen.estado));
              return (
                <li key={i} className="flex items-center gap-3 px-3 py-2 text-sm">
                  {f.imagen?.url_anotada ? (
                    <img src={f.imagen.url_anotada} alt="" className="h-12 w-16 shrink-0 rounded-md bg-slate-800 object-cover" />
                  ) : (
                    <span className="flex h-12 w-16 shrink-0 items-center justify-center rounded-md bg-slate-100">
                      {enCurso && <LoaderCircle className="size-4 animate-spin text-slate-400" aria-hidden />}
                    </span>
                  )}
                  <span className="min-w-0 flex-1 truncate">{f.archivo}</span>
                  <span className="shrink-0 text-right">
                    {f.error ? <span className="text-red-700">{f.error}</span>
                      : f.imagen?.estado === "ERROR" ? <span className="text-red-700">No se pudo analizar</span>
                      : p ? (
                        <>
                          <b className={p.supera_umbral ? "text-vacio" : "text-green-700"}>{pct(p.porcentaje_vacio)}</b>
                          <span className="text-slate-500"> · {p.num_vacios} vacío{p.num_vacios === 1 ? "" : "s"} · {p.tiempo_inferencia_ms} ms</span>
                          {f.imagen?.ticket ? (
                            <Link to={`/tickets/${f.imagen.ticket.numero}`} onClick={cerrar} className="ml-2 font-semibold text-primario hover:underline">
                              {f.imagen.ticket.numero}{f.imagen.ticket.tipo === "SEGUIMIENTO" ? " (seguimiento)" : ""}
                            </Link>
                          ) : <span className="ml-2 text-slate-500">bajo el umbral</span>}
                        </>
                      ) : f.imagenId ? <span className="text-slate-500">Analizando…</span>
                      : <span className="text-slate-500">{subiendo ? "Subiendo…" : "En espera"}</span>}
                  </span>
                </li>
              );
            })}
          </ul>
        )}
        <p className="text-xs text-slate-500">
          También puedes dejar las fotos en la carpeta del servidor <code>entradas/{carpeta.replace("recintos/", "")}/{categoria?.nombre ?? "<CATEGORÍA>"}/</code>:
          el importador las toma solo cada pocos segundos.
        </p>
        <div className="flex justify-end gap-3">
          <Boton variante="secundario" onClick={cerrar}>{filas.length ? "Cerrar" : "Cancelar"}</Boton>
          <Boton onClick={subir} cargando={subiendo} disabled={!categoriaId || !archivos.length}>Subir y analizar</Boton>
        </div>
      </div>
    </Modal>
  );
}
