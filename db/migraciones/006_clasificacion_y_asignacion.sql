-- Entrada común, caracterización y avisos de servicio. No modifica resultados anteriores.
BEGIN;

ALTER TABLE imagen
    ADD COLUMN estado_caracterizacion TEXT NOT NULL DEFAULT 'NO_REQUERIDA'
        CHECK (estado_caracterizacion IN ('NO_REQUERIDA', 'PENDIENTE', 'PROCESANDO', 'AUTOMATICA', 'MANUAL', 'REVISION')),
    ADD COLUMN producto_caracterizado TEXT,
    ADD COLUMN caracterizacion_detalle JSONB NOT NULL DEFAULT '{}',
    ADD COLUMN caracterizada_por INTEGER REFERENCES usuario(id),
    ADD COLUMN caracterizada_en TIMESTAMPTZ,
    ADD COLUMN version_caracterizacion INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN importacion_clave TEXT UNIQUE;
CREATE INDEX ix_imagen_caracterizacion_recinto
    ON imagen (recinto_id, estado_caracterizacion, recibida_en);
CREATE UNIQUE INDEX ux_tarea_clasificacion_pendiente
    ON tarea (((payload ->> 'imagen_id')::BIGINT))
    WHERE tipo = 'CLASIFICAR_IMAGEN' AND estado IN ('PENDIENTE', 'PROCESANDO');

CREATE TABLE incidencia_ia (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    proveedor VARCHAR(40) NOT NULL,
    modelo VARCHAR(120) NOT NULL,
    motivo TEXT NOT NULL CHECK (motivo IN ('LIMITE_TEMPORAL', 'CUOTA', 'LIMITE_USO', 'ERROR', 'CONFIGURACION')),
    mensaje TEXT NOT NULL,
    reintentar_en TIMESTAMPTZ,
    creada_en TIMESTAMPTZ NOT NULL DEFAULT now(),
    resuelta_en TIMESTAMPTZ
);
CREATE UNIQUE INDEX ux_incidencia_ia_activa ON incidencia_ia (proveedor, modelo)
    WHERE resuelta_en IS NULL;
CREATE TABLE incidencia_ia_recinto (
    incidencia_id BIGINT NOT NULL REFERENCES incidencia_ia(id) ON DELETE CASCADE,
    recinto_id INTEGER NOT NULL REFERENCES recinto(id),
    PRIMARY KEY (incidencia_id, recinto_id)
);
ALTER TABLE notificacion ADD COLUMN incidente_ia_id BIGINT REFERENCES incidencia_ia(id);
CREATE UNIQUE INDEX ux_notificacion_incidencia_usuario ON notificacion (usuario_id, incidente_ia_id)
    WHERE incidente_ia_id IS NOT NULL;

CREATE FUNCTION fn_encolar_clasificacion(p_imagen_id BIGINT) RETURNS BIGINT
LANGUAGE plpgsql AS $$
DECLARE
    v_imagen imagen%ROWTYPE;
    v_tarea BIGINT;
BEGIN
    SELECT * INTO STRICT v_imagen FROM imagen WHERE id = p_imagen_id FOR UPDATE;
    IF v_imagen.estado_caracterizacion IN ('MANUAL', 'AUTOMATICA') THEN
        RETURN NULL;
    END IF;
    SELECT id INTO v_tarea FROM tarea
     WHERE tipo = 'CLASIFICAR_IMAGEN' AND estado IN ('PENDIENTE', 'PROCESANDO')
       AND (payload ->> 'imagen_id')::BIGINT = p_imagen_id
     ORDER BY id LIMIT 1;
    IF FOUND THEN RETURN v_tarea; END IF;
    UPDATE imagen SET estado_caracterizacion = 'PENDIENTE' WHERE id = p_imagen_id;
    INSERT INTO tarea (tipo, recinto_id, payload)
    VALUES ('CLASIFICAR_IMAGEN', v_imagen.recinto_id, jsonb_build_object('imagen_id', p_imagen_id))
    RETURNING id INTO v_tarea;
    RETURN v_tarea;
END $$;

CREATE FUNCTION fn_avisar_incidencia_ia(p_incidente_id BIGINT) RETURNS INTEGER
LANGUAGE plpgsql AS $$
DECLARE
    v_total INTEGER;
BEGIN
    INSERT INTO notificacion (usuario_id, tipo, mensaje, incidente_ia_id)
    SELECT DISTINCT u.id, 'IA_CUOTA'::tipo_notificacion,
           left(CASE i.motivo
                WHEN 'CUOTA' THEN 'La IA de caracterización alcanzó su cuota. Revisa las imágenes pendientes de tu sucursal.'
                WHEN 'CONFIGURACION' THEN 'La IA de caracterización requiere configuración. Puedes caracterizar las imágenes manualmente.'
                WHEN 'LIMITE_TEMPORAL' THEN 'La caracterización automática está pausada temporalmente. Puedes revisar las imágenes pendientes.'
                ELSE 'La caracterización automática no está disponible. Puedes completar las imágenes manualmente.' END, 255),
           i.id
      FROM incidencia_ia i
      JOIN incidencia_ia_recinto ir ON ir.incidencia_id = i.id
      JOIN usuario_recinto ur ON ur.recinto_id = ir.recinto_id
      JOIN usuario u ON u.id = ur.usuario_id
     WHERE i.id = p_incidente_id AND i.resuelta_en IS NULL AND u.activo AND u.rol = 'SUPERVISOR'
    ON CONFLICT DO NOTHING;
    GET DIAGNOSTICS v_total = ROW_COUNT;
    RETURN v_total;
END $$;

-- Un único orden de bloqueo por sucursal para asignaciones automáticas y manuales.
CREATE FUNCTION fn_autoasignar_ticket(p_ticket_id BIGINT) RETURNS INTEGER
LANGUAGE plpgsql AS $$
DECLARE
    v_recinto INTEGER;
    v_ticket ticket%ROWTYPE;
    v_reponedor INTEGER;
    v_actor TEXT := current_setting('app.usuario_id', true);
BEGIN
    SELECT recinto_id INTO STRICT v_recinto FROM ticket WHERE id = p_ticket_id;
    PERFORM pg_advisory_xact_lock(727006, v_recinto);
    SELECT * INTO STRICT v_ticket FROM ticket WHERE id = p_ticket_id FOR UPDATE;
    IF v_ticket.asignado_a IS NOT NULL OR v_ticket.estado <> 'ABIERTO' THEN
        RETURN v_ticket.asignado_a;
    END IF;
    SELECT u.id INTO v_reponedor
      FROM usuario u JOIN usuario_recinto ur ON ur.usuario_id = u.id
     WHERE ur.recinto_id = v_recinto AND u.activo AND u.rol = 'REPONEDOR'
     ORDER BY (SELECT count(*) FROM ticket t WHERE t.recinto_id = v_recinto
                  AND t.asignado_a = u.id AND t.estado IN ('ASIGNADO', 'EN_PROGRESO')),
              (SELECT max(h.creado_en) FROM historial_ticket h JOIN ticket t ON t.id = h.ticket_id
                 WHERE h.asignado_nuevo = u.id AND t.recinto_id = v_recinto) NULLS FIRST,
              u.id
     LIMIT 1 FOR UPDATE OF u;
    IF v_reponedor IS NULL THEN RETURN NULL; END IF;
    -- La decisión la toma el sistema, no el usuario que subió la foto.
    PERFORM set_config('app.usuario_id', '', true);
    UPDATE ticket SET asignado_a = v_reponedor, asignado_por = NULL WHERE id = p_ticket_id;
    PERFORM set_config('app.usuario_id', COALESCE(v_actor, ''), true);
    RETURN v_reponedor;
EXCEPTION WHEN OTHERS THEN
    PERFORM set_config('app.usuario_id', COALESCE(v_actor, ''), true);
    RAISE;
END $$;

DROP INDEX ux_ticket_camara_abierto_por_categoria;

CREATE OR REPLACE FUNCTION fn_ticket_desde_prediccion(p_prediccion_id BIGINT) RETURNS BIGINT
LANGUAGE plpgsql AS $$
DECLARE
    p prediccion%ROWTYPE;
    i imagen%ROWTYPE;
    g gondola%ROWTYPE;
    v_cat categoria%ROWTYPE;
    v_tipo_cam VARCHAR(10);
    v_ticket BIGINT;
    v_lugar TEXT;
    v_fuente TEXT;
BEGIN
    SELECT * INTO STRICT p FROM prediccion WHERE id = p_prediccion_id;
    IF p.porcentaje_vacio IS NULL OR p.supera_umbral IS DISTINCT FROM TRUE THEN RETURN NULL; END IF;
    SELECT * INTO STRICT i FROM imagen WHERE id = p.imagen_id;
    PERFORM pg_advisory_xact_lock(727006, i.recinto_id);
    SELECT * INTO STRICT i FROM imagen WHERE id = p.imagen_id FOR UPDATE;
    -- Una evidencia de cierre nunca se convierte en un nuevo incidente.
    IF EXISTS (SELECT 1 FROM ticket_imagen WHERE imagen_id = i.id AND tipo = 'CIERRE') THEN RETURN NULL; END IF;
    SELECT ticket_id INTO v_ticket FROM ticket_imagen WHERE imagen_id = i.id ORDER BY agregada_en LIMIT 1;
    IF FOUND THEN RETURN v_ticket; END IF;
    SELECT * INTO g FROM gondola WHERE id = i.gondola_id;
    SELECT * INTO v_cat FROM categoria WHERE id = COALESCE(i.categoria_id, g.categoria_id);
    SELECT tipo INTO v_tipo_cam FROM camara WHERE id = i.camara_id;
    v_lugar := CASE WHEN g.id IS NOT NULL THEN g.codigo || COALESCE(' · ' || COALESCE(v_cat.nombre, g.categoria), '')
                    WHEN v_cat.id IS NOT NULL THEN v_cat.nombre
                    ELSE format('imagen %s · caracterización pendiente', i.id) END;
    v_fuente := CASE WHEN i.origen = 'MOVIL' THEN 'foto móvil'
                    WHEN v_tipo_cam = 'CARGA' THEN 'foto cargada' ELSE 'cámara' END;
    -- Solo una ubicación física conocida admite agrupar fotografías de seguimiento.
    IF i.origen = 'CAMARA' AND i.gondola_id IS NOT NULL THEN
        SELECT id INTO v_ticket FROM ticket
         WHERE origen = 'CAMARA' AND gondola_id = i.gondola_id
           AND estado IN ('ABIERTO', 'ASIGNADO', 'EN_PROGRESO') FOR UPDATE;
        IF FOUND THEN
            INSERT INTO ticket_imagen (ticket_id, imagen_id, tipo) VALUES (v_ticket, i.id, 'SEGUIMIENTO')
            ON CONFLICT DO NOTHING;
            UPDATE ticket SET porcentaje_vacio = p.porcentaje_vacio,
                   prioridad = GREATEST(prioridad, fn_prioridad_por_vacio(p.porcentaje_vacio)) WHERE id = v_ticket;
            RETURN v_ticket;
        END IF;
    END IF;
    INSERT INTO ticket (titulo, descripcion, prioridad, origen, recinto_id, gondola_id, categoria_id,
                        porcentaje_vacio, creado_por, asignado_a)
    VALUES (format('Vacío detectado en %s', v_lugar),
            format('Ticket generado automáticamente desde %s. El modelo detectó %s %% de vacío (umbral %s %%).',
                   v_fuente, replace(p.porcentaje_vacio::TEXT, '.', ','), replace(p.umbral_aplicado::TEXT, '.', ',')),
            fn_prioridad_por_vacio(p.porcentaje_vacio), i.origen::TEXT::origen_ticket,
            i.recinto_id, i.gondola_id, v_cat.id, p.porcentaje_vacio, i.subida_por, NULL)
    RETURNING id INTO v_ticket;
    INSERT INTO ticket_imagen (ticket_id, imagen_id, tipo) VALUES (v_ticket, i.id, 'APERTURA');
    INSERT INTO notificacion (usuario_id, ticket_id, tipo, mensaje)
    SELECT u.id, v_ticket, 'ALERTA_VACIO', left(format('%s %% de vacío en %s',
             replace(p.porcentaje_vacio::TEXT, '.', ','), v_lugar), 255)
      FROM usuario u JOIN usuario_recinto ur ON ur.usuario_id = u.id
     WHERE ur.recinto_id = i.recinto_id AND u.rol = 'SUPERVISOR' AND u.activo;
    PERFORM fn_autoasignar_ticket(v_ticket);
    RETURN v_ticket;
END $$;

CREATE FUNCTION fn_aplicar_caracterizacion(p_imagen_id BIGINT) RETURNS VOID
LANGUAGE plpgsql AS $$
DECLARE
    i imagen%ROWTYPE;
    v_categoria TEXT;
BEGIN
    SELECT * INTO STRICT i FROM imagen WHERE id = p_imagen_id FOR UPDATE;
    IF i.estado_caracterizacion NOT IN ('AUTOMATICA', 'MANUAL') THEN RETURN; END IF;
    SELECT nombre INTO v_categoria FROM categoria WHERE id = i.categoria_id;
    UPDATE ticket t
       SET categoria_id = COALESCE(i.categoria_id, t.categoria_id),
           categoria_producto = CASE WHEN i.estado_caracterizacion = 'MANUAL' OR t.categoria_producto IS NULL OR t.enriquecido_ia
                     THEN COALESCE(v_categoria, t.categoria_producto) ELSE t.categoria_producto END,
           titulo = CASE WHEN t.titulo = format('Vacío detectado en imagen %s · caracterización pendiente', i.id)
                               AND v_categoria IS NOT NULL THEN format('Vacío detectado en %s', v_categoria) ELSE t.titulo END
     WHERE EXISTS (SELECT 1 FROM ticket_imagen ti WHERE ti.ticket_id = t.id AND ti.imagen_id = i.id AND ti.tipo <> 'CIERRE')
       AND (i.gondola_id IS NULL OR NOT EXISTS (
           SELECT 1 FROM ticket_imagen otro JOIN ticket_imagen actual ON actual.ticket_id = otro.ticket_id
            WHERE actual.imagen_id = i.id AND actual.ticket_id = t.id AND otro.tipo <> 'CIERRE'
              AND (otro.agregada_en, otro.imagen_id) > (actual.agregada_en, actual.imagen_id)));
END $$;

CREATE TRIGGER trg_evento_caracterizacion
    AFTER UPDATE OF estado_caracterizacion, categoria_id, producto_caracterizado ON imagen
    FOR EACH ROW EXECUTE FUNCTION fn_evento_imagen();

COMMIT;
