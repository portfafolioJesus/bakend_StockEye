-- =====================================================================
--  StockEye · 003 · Carga de fotos reales por carpeta y desde el panel
--  Cada góndola puede tener una "fuente de carga" (cámara de tipo CARGA):
--  las fotos que se dejan en entradas/<RECINTO>/<GÓNDOLA>/ o que se suben
--  desde el panel se tratan como fotos de cámara (abren ticket solas y las
--  siguientes quedan como SEGUIMIENTO), sin aparecer como cámara sin señal.
-- =====================================================================

BEGIN;

ALTER TABLE camara
    ADD COLUMN tipo VARCHAR(10) NOT NULL DEFAULT 'IP' CHECK (tipo IN ('IP', 'CARGA'));

-- Una sola fuente de carga por góndola
CREATE UNIQUE INDEX ux_camara_carga_por_gondola ON camara (gondola_id) WHERE tipo = 'CARGA';

-- Devuelve (y crea si falta) la fuente de carga de una góndola.
CREATE FUNCTION fn_fuente_carga(p_gondola_id INTEGER) RETURNS INTEGER
LANGUAGE plpgsql AS $$
DECLARE
    v_id     INTEGER;
    g        gondola%ROWTYPE;
    v_rec    TEXT;
    v_codigo TEXT;
BEGIN
    SELECT id INTO v_id FROM camara WHERE gondola_id = p_gondola_id AND tipo = 'CARGA';
    IF FOUND THEN
        UPDATE camara SET activa = TRUE WHERE id = v_id AND NOT activa;
        RETURN v_id;
    END IF;
    SELECT * INTO STRICT g FROM gondola WHERE id = p_gondola_id;
    SELECT codigo INTO v_rec FROM recinto WHERE id = g.recinto_id;
    v_codigo := v_rec || '-CARGA-' || g.codigo;
    IF length(v_codigo) > 30 THEN
        v_codigo := v_rec || '-CARGA-' || g.id;
    END IF;
    INSERT INTO camara (recinto_id, gondola_id, codigo, nombre, url_stream, api_key_hash,
                        intervalo_captura_seg, tipo)
    VALUES (g.recinto_id, g.id, v_codigo, 'Fotos cargadas · ' || g.codigo,
            'carpeta://' || v_rec || '/' || g.codigo,
            'sin-api-key$' || md5(random()::TEXT || clock_timestamp()::TEXT),   -- no recibe por /ingesta
            86400, 'CARGA')
    RETURNING id INTO v_id;
    RETURN v_id;
END $$;

-- Las fuentes de carga no tienen "señal": siempre cuentan como disponibles.
CREATE OR REPLACE VIEW v_camara_estado AS
SELECT
    c.id,
    c.recinto_id,
    r.codigo AS recinto_codigo,
    c.gondola_id,
    g.codigo AS gondola_codigo,
    g.categoria,
    c.codigo,
    c.nombre,
    c.url_stream,
    c.intervalo_captura_seg,
    c.activa,
    c.ultima_captura,
    c.roi,
    c.ultimo_error,
    c.ultimo_error_en,
    CASE WHEN c.tipo = 'CARGA' THEN c.activa
         ELSE (c.activa AND c.ultima_captura IS NOT NULL
               AND c.ultima_captura > now() - make_interval(secs => 2 * c.intervalo_captura_seg))
    END AS en_linea,
    c.tipo
FROM camara c
JOIN recinto r      ON r.id = c.recinto_id
LEFT JOIN gondola g ON g.id = c.gondola_id;

-- La bandeja distingue "cámara" de "foto cargada".
CREATE OR REPLACE VIEW v_ticket_resumen AS
SELECT
    t.id,
    t.numero,
    t.titulo,
    t.estado,
    t.prioridad,
    t.origen,
    t.porcentaje_vacio,
    t.producto_faltante,
    t.enriquecido_ia,
    r.id      AS recinto_id,
    r.codigo  AS recinto_codigo,
    g.codigo  AS gondola_codigo,
    g.categoria,
    t.asignado_a,
    ua.nombre || ' ' || ua.apellido AS asignado_nombre,
    uc.nombre || ' ' || uc.apellido AS creado_por_nombre,
    t.creado_en,
    t.asignado_en,
    t.cerrado_en,
    ROUND(EXTRACT(EPOCH FROM (COALESCE(t.cerrado_en, now()) - t.creado_en)) / 60)::INTEGER
        AS minutos_abierto,
    (SELECT count(*) FROM comentario c WHERE c.ticket_id = t.id) AS num_comentarios,
    EXISTS (
        SELECT 1
        FROM ticket_imagen ti
        JOIN prediccion pr ON pr.imagen_id = ti.imagen_id
        WHERE ti.ticket_id = t.id
          AND ti.tipo = 'CIERRE'
          AND NOT pr.supera_umbral
    ) AS cierre_verificado,
    t.gondola_id,
    g.pasillo,
    t.creado_por,
    t.categoria_producto,
    t.descripcion,
    t.actualizado_en,
    ub.nombre || ' ' || ub.apellido AS asignado_por_nombre,
    r.umbral_vacio,
    (SELECT c.codigo
       FROM ticket_imagen ti JOIN imagen i ON i.id = ti.imagen_id JOIN camara c ON c.id = i.camara_id
      WHERE ti.ticket_id = t.id AND ti.tipo = 'APERTURA' LIMIT 1) AS camara_codigo,
    (SELECT pr.porcentaje_vacio
       FROM ticket_imagen ti JOIN prediccion pr ON pr.imagen_id = ti.imagen_id
      WHERE ti.ticket_id = t.id AND ti.tipo = 'APERTURA'
      ORDER BY pr.creada_en LIMIT 1) AS pct_apertura,
    (SELECT pr.porcentaje_vacio
       FROM ticket_imagen ti JOIN prediccion pr ON pr.imagen_id = ti.imagen_id
      WHERE ti.ticket_id = t.id AND ti.tipo = 'CIERRE'
      ORDER BY ti.agregada_en DESC, pr.creada_en DESC LIMIT 1) AS pct_cierre,
    -- nueva (003)
    (SELECT c.tipo
       FROM ticket_imagen ti JOIN imagen i ON i.id = ti.imagen_id JOIN camara c ON c.id = i.camara_id
      WHERE ti.ticket_id = t.id AND ti.tipo = 'APERTURA' LIMIT 1) AS camara_tipo
FROM ticket t
JOIN recinto r       ON r.id  = t.recinto_id
LEFT JOIN gondola g  ON g.id  = t.gondola_id
LEFT JOIN usuario ua ON ua.id = t.asignado_a
LEFT JOIN usuario uc ON uc.id = t.creado_por
LEFT JOIN usuario ub ON ub.id = t.asignado_por;

COMMIT;
