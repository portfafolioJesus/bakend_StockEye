import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router";
import { api } from "../lib/api";
import type { Carga, DetalleTicket, Gondola } from "../lib/tipos";
import { Boton, Modal, useAvisos } from "./ui";

export function NuevoTicket({ abierto, onCerrar, recintoId, equipo }: {
  abierto: boolean; onCerrar: () => void; recintoId: number; equipo: Carga[];
}) {
  const [f, setF] = useState({ titulo: "", gondola_id: "", prioridad: "MEDIA", asignado_a: "", descripcion: "", producto_faltante: "" });
  const qc = useQueryClient();
  const ir = useNavigate();
  const avisar = useAvisos();
  const { data: gondolas = [] } = useQuery({
    queryKey: ["gondolas", recintoId],
    queryFn: () => api<Gondola[]>(`/recintos/${recintoId}/gondolas`),
    enabled: abierto,
  });
  const crear = useMutation({
    mutationFn: () =>
      api<DetalleTicket>("/tickets", {
        cuerpo: {
          recinto_id: recintoId,
          titulo: f.titulo,
          gondola_id: f.gondola_id ? Number(f.gondola_id) : null,
          prioridad: f.prioridad,
          asignado_a: f.asignado_a ? Number(f.asignado_a) : null,
          descripcion: f.descripcion || null,
          producto_faltante: f.producto_faltante || null,
        },
      }),
    onSuccess: (d) => {
      qc.invalidateQueries({ queryKey: ["tickets"] });
      avisar(`Ticket ${d.ticket.numero} creado`);
      onCerrar();
      ir(`/tickets/${d.ticket.numero}`);
    },
    onError: (e: Error) => avisar(e.message, "error"),
  });
  const cambiar = (k: keyof typeof f) => (e: { target: { value: string } }) => setF((x) => ({ ...x, [k]: e.target.value }));
  const enviar = (e: FormEvent) => {
    e.preventDefault();
    crear.mutate();
  };
  return (
    <Modal abierto={abierto} titulo="Nuevo ticket manual" onCerrar={onCerrar}>
      <form onSubmit={enviar} className="flex flex-col gap-4">
        <label>
          <span className="etiqueta">Título</span>
          <input className="campo" required minLength={3} value={f.titulo} onChange={cambiar("titulo")} placeholder="Ej.: Quiebre de stock en P04-G01" />
        </label>
        <div className="grid gap-4 sm:grid-cols-2">
          <label>
            <span className="etiqueta">Góndola</span>
            <select className="campo" value={f.gondola_id} onChange={cambiar("gondola_id")}>
              <option value="">Sin góndola</option>
              {gondolas.map((g) => <option key={g.id} value={g.id}>{g.codigo} · {g.categoria}</option>)}
            </select>
          </label>
          <label>
            <span className="etiqueta">Prioridad</span>
            <select className="campo" value={f.prioridad} onChange={cambiar("prioridad")}>
              <option value="BAJA">Baja</option>
              <option value="MEDIA">Media</option>
              <option value="ALTA">Alta</option>
              <option value="CRITICA">Crítica</option>
            </select>
          </label>
        </div>
        <label>
          <span className="etiqueta">Producto faltante (opcional)</span>
          <input className="campo" value={f.producto_faltante} onChange={cambiar("producto_faltante")} />
        </label>
        <label>
          <span className="etiqueta">Asignar a (opcional)</span>
          <select className="campo" value={f.asignado_a} onChange={cambiar("asignado_a")}>
            <option value="">Sin asignar</option>
            {equipo.map((u) => <option key={u.usuario_id} value={u.usuario_id}>{u.reponedor}</option>)}
          </select>
        </label>
        <label>
          <span className="etiqueta">Descripción</span>
          <textarea className="campo" rows={3} value={f.descripcion} onChange={cambiar("descripcion")} />
        </label>
        <div className="flex justify-end gap-3">
          <Boton type="button" variante="secundario" onClick={onCerrar}>Cancelar</Boton>
          <Boton type="submit" cargando={crear.isPending}>Crear ticket</Boton>
        </div>
      </form>
    </Modal>
  );
}
