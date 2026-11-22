-- =====================================================================
--  StockEye · 002 · Producción: colas, push, IA intercambiable, eventos
--  Se aplica después de 001_esquema.sql. No editar una vez aplicada:
--  los cambios nuevos van en 003_*.sql.
-- =====================================================================

BEGIN;

-- ---------------------------------------------------------------------
-- 1. Modelo de IA: familia, parámetros y métricas
-- ---------------------------------------------------------------------
CREATE TYPE familia_modelo AS ENUM ('SEGFORMER', 'YOLO');

ALTER TABLE modelo_ia
    ADD COLUMN familia       familia_modelo NOT NULL DEFAULT 'SEGFORMER',
    ADD COLUMN parametros    JSONB          NOT NULL DEFAULT '{}',   -- {"lado":1280,"pixeles_max":740000,...}
    ADD COLUMN metricas      JSONB          NOT NULL DEFAULT '{}',   -- {"iou_vacio":0.354,...} o {"map50":0.81}
    ADD COLUMN activado_en   TIMESTAMPTZ,
    ADD COLUMN activado_por  INTEGER REFERENCES usuario(id);

-- ---------------------------------------------------------------------
-- 2. Usuarios, cámaras e imágenes
-- ---------------------------------------------------------------------
ALTER TABLE usuario
    ADD COLUMN debe_cambiar_clave    BOOLEAN     NOT NULL DEFAULT FALSE,
    ADD COLUMN ultimo_acceso_origen  VARCHAR(10);                    -- 'web' | 'app'

ALTER TABLE camara
    ADD COLUMN roi              JSONB,          -- [[x,y],...] normalizado 0..1: zona de la góndola
    ADD COLUMN ultimo_error     TEXT,
    ADD COLUMN ultimo_error_en  TIMESTAMPTZ;

-- Lease de la cola de inferencia: quién tomó la imagen y cuándo.
ALTER TABLE imagen
    ADD COLUMN intentos      SMALLINT    NOT NULL DEFAULT 0,
    ADD COLUMN tomada_por    VARCHAR(80),
    ADD COLUMN tomada_en     TIMESTAMPTZ,
    ADD COLUMN procesada_en  TIMESTAMPTZ;
CREATE INDEX ix_imagen_pendiente_recinto ON imagen (recinto_id, recibida_en) WHERE estado = 'PENDIENTE';
CREATE INDEX ix_imagen_procesando        ON imagen (tomada_en)               WHERE estado = 'PROCESANDO';

ALTER TABLE notificacion
    ADD COLUMN intentos_push    SMALLINT NOT NULL DEFAULT 0,
    ADD COLUMN push_error       TEXT,
    ADD COLUMN push_enviada_en  TIMESTAMPTZ;

-- La foto móvil se analiza con IA ANTES de crear el ticket (pantalla
-- "Resultado del análisis"), así que el análisis puede no tener ticket aún.
ALTER TABLE analisis_ia ALTER COLUMN ticket_id DROP NOT NULL;
CREATE INDEX ix_analisis_ia_imagen ON analisis_ia (imagen_id);

-- ---------------------------------------------------------------------
-- 3. Notificaciones push
-- ---------------------------------------------------------------------
CREATE TABLE dispositivo_push (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    usuario_id      INTEGER      NOT NULL REFERENCES usuario(id) ON DELETE CASCADE,
    token           VARCHAR(512) NOT NULL UNIQUE,                    -- token FCM
    plataforma      VARCHAR(20)  NOT NULL DEFAULT 'ANDROID',
    creado_en       TIMESTAMPTZ  NOT NULL DEFAULT now(),
    actualizado_en  TIMESTAMPTZ  NOT NULL DEFAULT now()
);
CREATE INDEX ix_dispositivo_push_usuario ON dispositivo_push (usuario_id);

CREATE TABLE web_push_suscripcion (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    usuario_id  INTEGER     NOT NULL REFERENCES usuario(id) ON DELETE CASCADE,
    endpoint    TEXT        NOT NULL UNIQUE,
    p256dh      TEXT        NOT NULL,
    auth        TEXT        NOT NULL,
    user_agent  VARCHAR(255),
    creado_en   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ix_web_push_usuario ON web_push_suscripcion (usuario_id);

-- ---------------------------------------------------------------------
-- 4. Integración de IA (una sola fila). La API key NUNCA va aquí:
--    vive en variables de entorno / gestor de secretos.
-- ---------------------------------------------------------------------
CREATE TABLE configuracion_ia (
    id                  SMALLINT     PRIMARY KEY DEFAULT 1 CHECK (id = 1),
    activo              BOOLEAN      NOT NULL DEFAULT FALSE,
    proveedor           VARCHAR(40)  NOT NULL DEFAULT 'groq',
    modelo              VARCHAR(120) NOT NULL DEFAULT 'qwen/qwen3.8-27b',
    recortar_a_gondola  BOOLEAN      NOT NULL DEFAULT TRUE,
    actualizado_en      TIMESTAMPTZ  NOT NULL DEFAULT now(),
    actualizado_por     INTEGER      REFERENCES usuario(id)
);
INSERT INTO configuracion_ia DEFAULT VALUES;

-- ---------------------------------------------------------------------
-- 5. Cola genérica de tareas (hoy: ANALISIS_IA). Se consume con
--    FOR UPDATE SKIP LOCKED desde el microservicio que corresponda.
-- ---------------------------------------------------------------------
CREATE TYPE tipo_tarea   AS ENUM ('ANALISIS_IA');
CREATE TYPE estado_tarea AS ENUM ('PENDIENTE', 'PROCESANDO', 'HECHA', 'ERROR');

CREATE TABLE tarea (
    id             BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tipo           tipo_tarea   NOT NULL,
    recinto_id     INTEGER      REFERENCES recinto(id),
    payload        JSONB        NOT NULL DEFAULT '{}',
    estado         estado_tarea NOT NULL DEFAULT 'PENDIENTE',
    intentos       SMALLINT     NOT NULL DEFAULT 0,
    disponible_en  TIMESTAMPTZ  NOT NULL DEFAULT now(),   -- reintentos con espera
    tomada_por     VARCHAR(80),
    tomada_en      TIMESTAMPTZ,
    error          TEXT,
    creada_en      TIMESTAMPTZ  NOT NULL DEFAULT now(),
    terminada_en   TIMESTAMPTZ
);
CREATE INDEX ix_tarea_pendiente ON tarea (tipo, disponible_en) WHERE estado = 'PENDIENTE';
CREATE INDEX ix_tarea_imagen    ON tarea (((payload ->> 'imagen_id')::BIGINT)) WHERE tipo = 'ANALISIS_IA';

-- Encola (o actualiza) el análisis de IA de una imagen. Devuelve el id de
-- la tarea o NULL si la IA está apagada o la imagen ya fue analizada.
CREATE FUNCTION fn_encolar_analisis_ia(p_imagen_id BIGINT, p_ticket_id BIGINT DEFAULT NULL)
RETURNS BIGINT LANGUAGE plpgsql AS $$
DECLARE
    v_id BIGINT;
    a    analisis_ia%ROWTYPE;
BEGIN
    -- ¿Ya se analizó? (p. ej. la foto móvil antes de crear el ticket) → enlazar y aplicar.
    SELECT * INTO a FROM analisis_ia
     WHERE imagen_id = p_imagen_id AND exitoso
     ORDER BY creado_en DESC LIMIT 1;
    IF FOUND THEN
        IF p_ticket_id IS NOT NULL THEN
            UPDATE analisis_ia SET ticket_id = p_ticket_id WHERE id = a.id AND ticket_id IS NULL;
            PERFORM fn_aplicar_analisis_ia(a.id, p_ticket_id);
        END IF;
        RETURN NULL;
    END IF;

    -- ¿Ya está en cola? → solo agregar el ticket al payload.
    UPDATE tarea
       SET payload = payload || jsonb_build_object('ticket_id', p_ticket_id)
     WHERE tipo = 'ANALISIS_IA'
       AND estado IN ('PENDIENTE', 'PROCESANDO')
       AND (payload ->> 'imagen_id')::BIGINT = p_imagen_id
       AND p_ticket_id IS NOT NULL
    RETURNING id INTO v_id;
    IF FOUND THEN RETURN v_id; END IF;
    IF EXISTS (SELECT 1 FROM tarea WHERE tipo = 'ANALISIS_IA' AND estado IN ('PENDIENTE', 'PROCESANDO')
                                     AND (payload ->> 'imagen_id')::BIGINT = p_imagen_id) THEN
        RETURN NULL;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM configuracion_ia WHERE activo) THEN
        RETURN NULL;
    END IF;

    INSERT INTO tarea (tipo, recinto_id, payload)
    SELECT 'ANALISIS_IA', i.recinto_id, jsonb_build_object('imagen_id', i.id, 'ticket_id', p_ticket_id)
      FROM imagen i WHERE i.id = p_imagen_id
    RETURNING id INTO v_id;
    RETURN v_id;
END $$;

-- Copia el mejor producto del análisis al ticket si nadie lo escribió a mano.
CREATE FUNCTION fn_aplicar_analisis_ia(p_analisis_id BIGINT, p_ticket_id BIGINT)
RETURNS VOID LANGUAGE plpgsql AS $$
DECLARE
    v_producto  TEXT;
    v_categoria TEXT;
BEGIN
    SELECT productos_faltantes -> 0 ->> 'producto', productos_faltantes -> 0 ->> 'categoria'
      INTO v_producto, v_categoria
      FROM analisis_ia WHERE id = p_analisis_id AND exitoso;
    IF v_producto IS NULL OR p_ticket_id IS NULL THEN
        RETURN;
    END IF;
    UPDATE ticket
       SET producto_faltante  = COALESCE(producto_faltante, left(v_producto, 150)),
           categoria_producto = COALESCE(categoria_producto, left(v_categoria, 80)),
           enriquecido_ia     = enriquecido_ia OR producto_faltante IS NULL
     WHERE id = p_ticket_id;
END $$;

-- Devuelve a la cola las imágenes cuyo worker murió a mitad de camino.
-- Tras 3 intentos fallidos la imagen queda en ERROR.
CREATE FUNCTION fn_recuperar_imagenes(p_minutos INTEGER DEFAULT 5, p_max_intentos INTEGER DEFAULT 3)
RETURNS INTEGER LANGUAGE plpgsql AS $$
DECLARE
    v_n INTEGER;
BEGIN
    UPDATE imagen
       SET estado = CASE WHEN intentos >= p_max_intentos THEN 'ERROR'::estado_procesamiento ELSE 'PENDIENTE' END,
           error_detalle = CASE WHEN intentos >= p_max_intentos
                                THEN 'Se agotaron los intentos (el worker se detuvo durante la inferencia)'
                                ELSE error_detalle END,
           tomada_por = NULL
     WHERE estado = 'PROCESANDO'
       AND tomada_en < now() - make_interval(mins => p_minutos);
    GET DIAGNOSTICS v_n = ROW_COUNT;
    UPDATE tarea
       SET estado = CASE WHEN intentos >= p_max_intentos THEN 'ERROR'::estado_tarea ELSE 'PENDIENTE' END,
           tomada_por = NULL
     WHERE estado = 'PROCESANDO'
       AND tomada_en < now() - make_interval(mins => p_minutos);
    RETURN v_n;
END $$;

-- ---------------------------------------------------------------------
-- 6. Notificaciones de negocio adicionales
-- ---------------------------------------------------------------------
-- Comentario nuevo: avisa al reponedor asignado y, si comenta el
-- reponedor, a los supervisores del recinto.
CREATE FUNCTION fn_comentario_notificar() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    t      ticket%ROWTYPE;
    v_rol  rol_usuario;
    v_txt  TEXT;
BEGIN
    SELECT * INTO t FROM ticket WHERE id = NEW.ticket_id;
    SELECT rol INTO v_rol FROM usuario WHERE id = NEW.usuario_id;
    v_txt := left(format('%s: %s', t.numero, NEW.texto), 255);
    IF t.asignado_a IS NOT NULL AND t.asignado_a <> NEW.usuario_id THEN
        INSERT INTO notificacion (usuario_id, ticket_id, tipo, mensaje)
        VALUES (t.asignado_a, t.id, 'COMENTARIO', v_txt);
    END IF;
    IF v_rol = 'REPONEDOR' THEN
        INSERT INTO notificacion (usuario_id, ticket_id, tipo, mensaje)
        SELECT u.id, t.id, 'COMENTARIO', v_txt
          FROM usuario u JOIN usuario_recinto ur ON ur.usuario_id = u.id
         WHERE ur.recinto_id = t.recinto_id AND u.rol = 'SUPERVISOR' AND u.activo AND u.id <> NEW.usuario_id;
    END IF;
    RETURN NULL;
END $$;
CREATE TRIGGER trg_comentario_notificar
    AFTER INSERT ON comentario
    FOR EACH ROW EXECUTE FUNCTION fn_comentario_notificar();

-- Ticket cerrado: avisa a los supervisores del recinto.
CREATE FUNCTION fn_ticket_cerrado_notificar() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.estado = 'CERRADO' AND OLD.estado <> 'CERRADO' THEN
        INSERT INTO notificacion (usuario_id, ticket_id, tipo, mensaje)
        SELECT u.id, NEW.id, 'TICKET_CERRADO', left(format('%s cerrado: %s', NEW.numero, NEW.titulo), 255)
          FROM usuario u JOIN usuario_recinto ur ON ur.usuario_id = u.id
         WHERE ur.recinto_id = NEW.recinto_id AND u.rol = 'SUPERVISOR' AND u.activo
           AND u.id IS DISTINCT FROM app_usuario_actual();
    END IF;
    RETURN NULL;
END $$;
CREATE TRIGGER trg_ticket_cerrado_notificar
    AFTER UPDATE OF estado ON ticket
    FOR EACH ROW EXECUTE FUNCTION fn_ticket_cerrado_notificar();

-- ---------------------------------------------------------------------
-- 7. Eventos (LISTEN/NOTIFY) que despiertan a los microservicios y
--    alimentan el tiempo real (SSE) del panel web.
-- ---------------------------------------------------------------------
CREATE FUNCTION fn_evento_imagen() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.estado = 'PENDIENTE' THEN
        PERFORM pg_notify('imagen_nueva', NEW.recinto_id::TEXT);
    ELSIF NEW.estado IN ('PROCESADA', 'ERROR') THEN
        PERFORM pg_notify('imagen_procesada', json_build_object(
            'imagen_id', NEW.id, 'recinto_id', NEW.recinto_id, 'estado', NEW.estado)::TEXT);
    END IF;
    RETURN NULL;
END $$;
CREATE TRIGGER trg_evento_imagen
    AFTER INSERT OR UPDATE OF estado ON imagen
    FOR EACH ROW EXECUTE FUNCTION fn_evento_imagen();

CREATE FUNCTION fn_evento_notificacion() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    PERFORM pg_notify('notificacion_nueva', json_build_object(
        'id', NEW.id, 'usuario_id', NEW.usuario_id, 'tipo', NEW.tipo, 'mensaje', NEW.mensaje,
        'ticket_id', NEW.ticket_id)::TEXT);
    RETURN NULL;
END $$;
CREATE TRIGGER trg_evento_notificacion
    AFTER INSERT ON notificacion
    FOR EACH ROW EXECUTE FUNCTION fn_evento_notificacion();

CREATE FUNCTION fn_evento_tarea() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    PERFORM pg_notify('tarea_nueva', NEW.tipo::TEXT);
    RETURN NULL;
END $$;
CREATE TRIGGER trg_evento_tarea
    AFTER INSERT ON tarea
    FOR EACH ROW EXECUTE FUNCTION fn_evento_tarea();

CREATE FUNCTION fn_evento_ticket() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    v_ticket BIGINT;
    v_tipo   TEXT := lower(TG_TABLE_NAME);
    t        ticket%ROWTYPE;
BEGIN
    -- to_jsonb evita referenciar un campo que no existe en la otra tabla.
    v_ticket := (to_jsonb(NEW) ->> CASE TG_TABLE_NAME WHEN 'ticket' THEN 'id' ELSE 'ticket_id' END)::BIGINT;
    SELECT * INTO t FROM ticket WHERE id = v_ticket;
    PERFORM pg_notify('ticket_evento', json_build_object(
        'recinto_id', t.recinto_id, 'ticket_id', t.id, 'numero', t.numero, 'estado', t.estado,
        'asignado_a', t.asignado_a, 'origen', v_tipo, 'op', lower(TG_OP))::TEXT);
    RETURN NULL;
END $$;
CREATE TRIGGER trg_evento_ticket
    AFTER INSERT OR UPDATE ON ticket
    FOR EACH ROW EXECUTE FUNCTION fn_evento_ticket();
CREATE TRIGGER trg_evento_comentario
    AFTER INSERT ON comentario
    FOR EACH ROW EXECUTE FUNCTION fn_evento_ticket();
CREATE TRIGGER trg_evento_ticket_imagen
    AFTER INSERT ON ticket_imagen
    FOR EACH ROW EXECUTE FUNCTION fn_evento_ticket();

-- Cambio de modelo activo o de su umbral → los workers recargan.
CREATE FUNCTION fn_evento_modelo() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.activo THEN
        PERFORM pg_notify('modelo_activado', NEW.id::TEXT);
    END IF;
    RETURN NULL;
END $$;
CREATE TRIGGER trg_evento_modelo
    AFTER INSERT OR UPDATE OF activo, umbral_confianza, parametros, ruta_pesos ON modelo_ia
    FOR EACH ROW EXECUTE FUNCTION fn_evento_modelo();

-- ---------------------------------------------------------------------
-- 8. Vistas para las pantallas
-- ---------------------------------------------------------------------
-- Se agregan columnas AL FINAL (requisito de CREATE OR REPLACE VIEW).
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
    -- columnas nuevas (002)
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
      ORDER BY ti.agregada_en DESC, pr.creada_en DESC LIMIT 1) AS pct_cierre
FROM ticket t
JOIN recinto r       ON r.id  = t.recinto_id
LEFT JOIN gondola g  ON g.id  = t.gondola_id
LEFT JOIN usuario ua ON ua.id = t.asignado_a
LEFT JOIN usuario uc ON uc.id = t.creado_por
LEFT JOIN usuario ub ON ub.id = t.asignado_por;

-- Estado de cada cámara: "en línea" si mandó foto dentro de 2× su intervalo.
CREATE VIEW v_camara_estado AS
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
    (c.activa AND c.ultima_captura IS NOT NULL
        AND c.ultima_captura > now() - make_interval(secs => 2 * c.intervalo_captura_seg)) AS en_linea
FROM camara c
JOIN recinto r      ON r.id = c.recinto_id
LEFT JOIN gondola g ON g.id = c.gondola_id;

COMMIT;
