-- =====================================================================
--  StockEye · 004 · Categorías de producto (estilo departamentos Walmart)
--
--  La unidad principal pasa a ser la CATEGORÍA (Lácteos, Despensa, Bebidas…):
--  es como se reparte el trabajo en tienda y no cambia con el planograma.
--  La góndola queda como "punto fijo" OPCIONAL dentro de una categoría
--  (una cámara que siempre mira el mismo lugar).
--
--    * Foto con punto fijo    → como cámara: ticket nuevo o SEGUIMIENTO del abierto.
--    * Foto solo con categoría → reporte independiente: cada foto sobre el umbral
--                                abre su propio ticket (pueden ser góndolas distintas).
-- =====================================================================

BEGIN;

CREATE TABLE categoria (
    id            INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    codigo        VARCHAR(30) NOT NULL UNIQUE,                 -- 'LACTEOS'
    nombre        VARCHAR(80) NOT NULL UNIQUE,                 -- 'Lácteos y huevos'
    departamento  VARCHAR(60) NOT NULL,                        -- 'Frescos'
    orden         SMALLINT    NOT NULL DEFAULT 100,
    activo        BOOLEAN     NOT NULL DEFAULT TRUE
);

-- Catálogo inicial, agrupado como los departamentos de un hipermercado (Walmart/Líder)
INSERT INTO categoria (codigo, nombre, departamento, orden) VALUES
    ('ABARROTES',   'Abarrotes',                     'Despensa',            10),
    ('ACEITES',     'Aceites y aderezos',            'Despensa',            11),
    ('CONSERVAS',   'Conservas',                     'Despensa',            12),
    ('DESAYUNO',    'Desayuno y dulces',             'Despensa',            13),
    ('SNACKS',      'Snacks y galletas',             'Despensa',            14),
    ('LACTEOS',     'Lácteos y huevos',              'Frescos',             20),
    ('FIAMBRERIA',  'Fiambrería y quesos',           'Frescos',             21),
    ('PANADERIA',   'Panadería y pastelería',        'Frescos',             22),
    ('FRUTAS',      'Frutas y verduras',             'Frescos',             23),
    ('CARNES',      'Carnes y pescados',             'Frescos',             24),
    ('CONGELADOS',  'Congelados',                    'Frescos',             25),
    ('BEBIDAS',     'Bebidas y jugos',               'Bebidas y licores',   30),
    ('LICORES',     'Vinos, cervezas y licores',     'Bebidas y licores',   31),
    ('LIMPIEZA',    'Limpieza',                      'Limpieza y hogar',    40),
    ('PAPELES',     'Papeles y desechables',         'Limpieza y hogar',    41),
    ('HOGAR',       'Hogar y bazar',                 'Limpieza y hogar',    42),
    ('PERFUMERIA',  'Perfumería y cuidado personal', 'Cuidado personal',   50),
    ('BEBES',       'Bebés',                         'Cuidado personal',   51),
    ('MASCOTAS',    'Mascotas',                      'Mascotas',           60);

-- Normaliza texto para comparar nombres ("Lácteos" = "lacteos")
CREATE FUNCTION fn_normalizar(p TEXT) RETURNS TEXT
LANGUAGE sql IMMUTABLE AS $$
    SELECT translate(lower(btrim(p)), 'áàäâéèëêíìïîóòöôúùüûñç', 'aaaaeeeeiiiioooouuuunc')
$$;

-- Busca una categoría por código o nombre ("Lácteos" encuentra "Lácteos y huevos")
CREATE FUNCTION fn_buscar_categoria(p_texto TEXT) RETURNS INTEGER
LANGUAGE sql STABLE AS $$
    SELECT id FROM categoria
     WHERE activo AND (fn_normalizar(codigo) = fn_normalizar(p_texto)
                       OR fn_normalizar(nombre) = fn_normalizar(p_texto)
                       OR fn_normalizar(nombre) LIKE fn_normalizar(p_texto) || ' %')
     ORDER BY (fn_normalizar(nombre) = fn_normalizar(p_texto)) DESC, orden
     LIMIT 1
$$;

-- ---------------------------------------------------------------------
-- Góndola (punto fijo), imagen y ticket apuntan a la categoría
-- ---------------------------------------------------------------------
ALTER TABLE gondola ADD COLUMN categoria_id INTEGER REFERENCES categoria(id);
ALTER TABLE imagen  ADD COLUMN categoria_id INTEGER REFERENCES categoria(id);
ALTER TABLE ticket  ADD COLUMN categoria_id INTEGER REFERENCES categoria(id);
CREATE INDEX ix_ticket_categoria ON ticket (recinto_id, categoria_id, estado);
CREATE INDEX ix_imagen_categoria ON imagen (recinto_id, categoria_id, capturada_en DESC);

-- El texto gondola.categoria sigue al catálogo (lo usan vistas y la regla de tickets).
-- Si llega solo el texto (seed antiguo o carga manual), se busca en el catálogo.
CREATE FUNCTION fn_gondola_categoria() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.categoria_id IS NULL AND NEW.categoria IS NOT NULL THEN
        NEW.categoria_id := fn_buscar_categoria(NEW.categoria);
    END IF;
    IF NEW.categoria_id IS NOT NULL THEN
        SELECT nombre INTO NEW.categoria FROM categoria WHERE id = NEW.categoria_id;
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER trg_gondola_categoria
    BEFORE INSERT OR UPDATE OF categoria_id, categoria ON gondola
    FOR EACH ROW EXECUTE FUNCTION fn_gondola_categoria();

-- La foto hereda la categoría de su punto fijo si no se indicó
CREATE FUNCTION fn_imagen_categoria() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.categoria_id IS NULL AND NEW.gondola_id IS NOT NULL THEN
        SELECT categoria_id INTO NEW.categoria_id FROM gondola WHERE id = NEW.gondola_id;
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER trg_imagen_categoria
    BEFORE INSERT ON imagen
    FOR EACH ROW EXECUTE FUNCTION fn_imagen_categoria();

-- Datos existentes: góndolas, fotos y tickets quedan con su categoría
UPDATE gondola SET categoria = categoria WHERE categoria IS NOT NULL;   -- dispara el trigger
UPDATE imagen i SET categoria_id = g.categoria_id FROM gondola g WHERE g.id = i.gondola_id AND i.categoria_id IS NULL;
UPDATE ticket t SET categoria_id = g.categoria_id FROM gondola g WHERE g.id = t.gondola_id AND t.categoria_id IS NULL;

-- ---------------------------------------------------------------------
-- Fuente de carga por recinto (fotos solo con categoría, sin punto fijo)
-- ---------------------------------------------------------------------
CREATE UNIQUE INDEX ux_camara_carga_recinto ON camara (recinto_id) WHERE tipo = 'CARGA' AND gondola_id IS NULL;

CREATE FUNCTION fn_fuente_carga_recinto(p_recinto_id INTEGER) RETURNS INTEGER
LANGUAGE plpgsql AS $$
DECLARE
    v_id INTEGER;
BEGIN
    SELECT id INTO v_id FROM camara WHERE recinto_id = p_recinto_id AND tipo = 'CARGA' AND gondola_id IS NULL;
    IF FOUND THEN
        RETURN v_id;
    END IF;
    INSERT INTO camara (recinto_id, codigo, nombre, url_stream, api_key_hash, intervalo_captura_seg, tipo)
    SELECT r.id, r.codigo || '-CARGA', 'Fotos cargadas por categoría', 'carpeta://' || r.codigo,
           'sin-api-key$' || md5(random()::TEXT || clock_timestamp()::TEXT), 86400, 'CARGA'
      FROM recinto r WHERE r.id = p_recinto_id
    RETURNING id INTO v_id;
    RETURN v_id;
END $$;

-- Un solo ticket de cámara/carga activo por categoría y recinto (cuando no hay punto fijo)
CREATE UNIQUE INDEX ux_ticket_camara_abierto_por_categoria
    ON ticket (recinto_id, categoria_id)
    WHERE origen = 'CAMARA' AND gondola_id IS NULL AND estado IN ('ABIERTO', 'ASIGNADO', 'EN_PROGRESO');

-- ---------------------------------------------------------------------
-- Regla principal con categorías (reemplaza la de 001)
-- ---------------------------------------------------------------------
CREATE OR REPLACE FUNCTION fn_ticket_desde_prediccion(p_prediccion_id BIGINT) RETURNS BIGINT
LANGUAGE plpgsql AS $$
DECLARE
    p          prediccion%ROWTYPE;
    i          imagen%ROWTYPE;
    g          gondola%ROWTYPE;
    v_cat      categoria%ROWTYPE;
    v_tipo_cam VARCHAR(10);
    v_ticket   BIGINT;
    v_lugar    TEXT;
    v_fuente   TEXT;
BEGIN
    SELECT * INTO STRICT p FROM prediccion WHERE id = p_prediccion_id;
    IF NOT p.supera_umbral THEN
        RETURN NULL;
    END IF;

    SELECT * INTO STRICT i FROM imagen WHERE id = p.imagen_id;
    SELECT * INTO g FROM gondola WHERE id = i.gondola_id;
    SELECT * INTO v_cat FROM categoria WHERE id = COALESCE(i.categoria_id, g.categoria_id);
    SELECT tipo INTO v_tipo_cam FROM camara WHERE id = i.camara_id;

    v_lugar := CASE
        WHEN g.id IS NOT NULL THEN g.codigo || COALESCE(' · ' || COALESCE(v_cat.nombre, g.categoria), '')
        WHEN v_cat.id IS NOT NULL THEN v_cat.nombre
        ELSE 'góndola sin identificar' END;
    v_fuente := CASE
        WHEN i.origen = 'MOVIL' THEN 'foto móvil'
        WHEN v_tipo_cam = 'CARGA' THEN 'foto cargada'
        ELSE 'cámara' END;

    -- Cámara o carga: si ya hay un ticket activo del mismo punto fijo (o, sin punto fijo,
    -- de la misma categoría en el recinto), la foto es SEGUIMIENTO; al cerrarse, el próximo abre otro.
    IF i.origen = 'CAMARA' AND (i.gondola_id IS NOT NULL OR v_cat.id IS NOT NULL) THEN
        SELECT id INTO v_ticket
        FROM ticket
        WHERE origen = 'CAMARA'
          AND estado IN ('ABIERTO', 'ASIGNADO', 'EN_PROGRESO')
          AND CASE WHEN i.gondola_id IS NOT NULL THEN gondola_id = i.gondola_id
                   ELSE gondola_id IS NULL AND recinto_id = i.recinto_id AND categoria_id = v_cat.id END
        FOR UPDATE;

        IF FOUND THEN
            INSERT INTO ticket_imagen (ticket_id, imagen_id, tipo)
            VALUES (v_ticket, i.id, 'SEGUIMIENTO')
            ON CONFLICT DO NOTHING;

            UPDATE ticket
               SET porcentaje_vacio = p.porcentaje_vacio,
                   prioridad = GREATEST(prioridad, fn_prioridad_por_vacio(p.porcentaje_vacio))
             WHERE id = v_ticket;
            RETURN v_ticket;
        END IF;
    END IF;

    INSERT INTO ticket (titulo, descripcion, prioridad, origen, recinto_id, gondola_id, categoria_id,
                        porcentaje_vacio, creado_por, asignado_a)
    VALUES (
        format('Vacío detectado en %s', v_lugar),
        format('Ticket generado automáticamente desde %s. El modelo detectó %s %% de vacío (umbral %s %%).',
               v_fuente, replace(p.porcentaje_vacio::TEXT, '.', ','), replace(p.umbral_aplicado::TEXT, '.', ',')),
        fn_prioridad_por_vacio(p.porcentaje_vacio),
        i.origen::TEXT::origen_ticket,
        i.recinto_id,
        i.gondola_id,
        v_cat.id,
        p.porcentaje_vacio,
        i.subida_por,                                         -- NULL si vino de cámara o carga
        NULL                                                  -- todo ticket nuevo llega SIN ASIGNAR al supervisor
    )
    RETURNING id INTO v_ticket;

    INSERT INTO ticket_imagen (ticket_id, imagen_id, tipo)
    VALUES (v_ticket, i.id, 'APERTURA');

    -- Alerta a todos los supervisores activos del recinto
    INSERT INTO notificacion (usuario_id, ticket_id, tipo, mensaje)
    SELECT u.id, v_ticket, 'ALERTA_VACIO',
           left(format('%s %% de vacío en %s', replace(p.porcentaje_vacio::TEXT, '.', ','), v_lugar), 255)
    FROM usuario u
    JOIN usuario_recinto ur ON ur.usuario_id = u.id
    WHERE ur.recinto_id = i.recinto_id
      AND u.rol = 'SUPERVISOR'
      AND u.activo;

    RETURN v_ticket;
END $$;

-- ---------------------------------------------------------------------
-- Vistas: la categoría viene de la góndola o del propio ticket
-- ---------------------------------------------------------------------
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
    COALESCE(cat.nombre, g.categoria)::VARCHAR(80) AS categoria,
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
    (SELECT c.tipo
       FROM ticket_imagen ti JOIN imagen i ON i.id = ti.imagen_id JOIN camara c ON c.id = i.camara_id
      WHERE ti.ticket_id = t.id AND ti.tipo = 'APERTURA' LIMIT 1) AS camara_tipo,
    -- nuevas (004)
    COALESCE(t.categoria_id, g.categoria_id) AS categoria_id,
    cat.departamento
FROM ticket t
JOIN recinto r          ON r.id  = t.recinto_id
LEFT JOIN gondola g     ON g.id  = t.gondola_id
LEFT JOIN categoria cat ON cat.id = COALESCE(t.categoria_id, g.categoria_id)
LEFT JOIN usuario ua    ON ua.id = t.asignado_a
LEFT JOIN usuario uc    ON uc.id = t.creado_por
LEFT JOIN usuario ub    ON ub.id = t.asignado_por;

COMMIT;
