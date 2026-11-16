-- =====================================================================
--  StockEye · Detección de vacíos en góndolas
--  Esquema de base de datos · PostgreSQL 16 · v0.1
-- ---------------------------------------------------------------------
--  Ejecutar sobre una BD vacía:
--      createdb stockeye
--      psql -d stockeye -f schema.sql
--      psql -d stockeye -f seed_demo.sql      (datos de prueba, opcional)
--
--  Convenciones
--    * snake_case, nombres de tabla en singular, PK "id" IDENTITY.
--    * Fechas en TIMESTAMPTZ (la BD guarda UTC; la app muestra
--      America/Santiago).
--    * El backend identifica al usuario de cada transacción con
--          SET LOCAL app.usuario_id = '<id>';
--      Así los triggers saben quién cambió un ticket (NULL = sistema).
-- =====================================================================

BEGIN;

-- ---------------------------------------------------------------------
-- 1. Tipos enumerados
-- ---------------------------------------------------------------------
CREATE TYPE rol_usuario          AS ENUM ('ADMINISTRADOR', 'SUPERVISOR', 'REPONEDOR');
CREATE TYPE origen_imagen        AS ENUM ('CAMARA', 'MOVIL');
CREATE TYPE estado_procesamiento AS ENUM ('PENDIENTE', 'PROCESANDO', 'PROCESADA', 'ERROR');
CREATE TYPE origen_ticket        AS ENUM ('CAMARA', 'MOVIL', 'MANUAL');
CREATE TYPE estado_ticket        AS ENUM ('ABIERTO', 'ASIGNADO', 'EN_PROGRESO', 'CERRADO', 'CANCELADO');
CREATE TYPE prioridad_ticket     AS ENUM ('BAJA', 'MEDIA', 'ALTA', 'CRITICA');
CREATE TYPE tipo_evidencia       AS ENUM ('APERTURA', 'SEGUIMIENTO', 'CIERRE');
CREATE TYPE tipo_notificacion    AS ENUM ('ALERTA_VACIO', 'TICKET_ASIGNADO', 'TICKET_CERRADO', 'COMENTARIO');

-- ---------------------------------------------------------------------
-- 2. Organización: recintos, usuarios, góndolas y cámaras
-- ---------------------------------------------------------------------
CREATE TABLE recinto (
    id                INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    codigo            VARCHAR(20)  NOT NULL UNIQUE,            -- 'R01', 'R02'
    nombre            VARCHAR(120) NOT NULL,
    direccion         VARCHAR(200),
    comuna            VARCHAR(80),
    carpeta_imagenes  VARCHAR(255) NOT NULL UNIQUE,            -- 'recintos/R01'
    umbral_vacio      NUMERIC(5,2) NOT NULL DEFAULT 5.00
                      CHECK (umbral_vacio BETWEEN 0 AND 100),  -- % que dispara alerta
    activo            BOOLEAN      NOT NULL DEFAULT TRUE,
    creado_en         TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE TABLE usuario (
    id              INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    rut             VARCHAR(12)  UNIQUE,
    nombre          VARCHAR(80)  NOT NULL,
    apellido        VARCHAR(80)  NOT NULL,
    email           VARCHAR(160) NOT NULL,
    telefono        VARCHAR(20),
    password_hash   VARCHAR(255) NOT NULL,                     -- bcrypt / argon2, nunca texto plano
    rol             rol_usuario  NOT NULL,
    activo          BOOLEAN      NOT NULL DEFAULT TRUE,
    ultimo_acceso   TIMESTAMPTZ,
    creado_en       TIMESTAMPTZ  NOT NULL DEFAULT now(),
    actualizado_en  TIMESTAMPTZ  NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX ux_usuario_email ON usuario (lower(email));

-- Qué usuarios trabajan en qué recinto (N:M).
-- Un supervisor ve los tickets de sus recintos; un reponedor solo
-- puede recibir tickets de un recinto al que pertenece.
CREATE TABLE usuario_recinto (
    usuario_id  INTEGER NOT NULL REFERENCES usuario(id) ON DELETE CASCADE,
    recinto_id  INTEGER NOT NULL REFERENCES recinto(id) ON DELETE CASCADE,
    desde       DATE    NOT NULL DEFAULT CURRENT_DATE,
    PRIMARY KEY (usuario_id, recinto_id)
);
CREATE INDEX ix_usuario_recinto_recinto ON usuario_recinto (recinto_id);

CREATE TABLE gondola (
    id           INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    recinto_id   INTEGER      NOT NULL REFERENCES recinto(id),
    codigo       VARCHAR(20)  NOT NULL,                        -- 'P04-G01' (pasillo 4, góndola 1)
    pasillo      VARCHAR(20),
    categoria    VARCHAR(80),                                  -- 'Lácteos', 'Bebidas', ...
    descripcion  VARCHAR(200),
    activo       BOOLEAN      NOT NULL DEFAULT TRUE,
    UNIQUE (recinto_id, codigo),
    UNIQUE (id, recinto_id)          -- permite FKs compuestas (góndola del MISMO recinto)
);

CREATE TABLE camara (
    id                     INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    recinto_id             INTEGER      NOT NULL REFERENCES recinto(id),
    gondola_id             INTEGER,                            -- góndola que enfoca (opcional)
    codigo                 VARCHAR(30)  NOT NULL UNIQUE,       -- 'R01-CAM03'
    nombre                 VARCHAR(120),
    url_stream             VARCHAR(255),                       -- rtsp://... o endpoint de snapshot
    api_key_hash           VARCHAR(255) NOT NULL,              -- autentica el POST de ingesta
    intervalo_captura_seg  INTEGER      NOT NULL DEFAULT 300 CHECK (intervalo_captura_seg >= 30),
    activa                 BOOLEAN      NOT NULL DEFAULT TRUE,
    ultima_captura         TIMESTAMPTZ,
    creado_en              TIMESTAMPTZ  NOT NULL DEFAULT now(),
    UNIQUE (id, recinto_id),
    FOREIGN KEY (gondola_id, recinto_id) REFERENCES gondola (id, recinto_id)
);

-- ---------------------------------------------------------------------
-- 3. Visión: modelo YOLO, imágenes, predicciones y detecciones
-- ---------------------------------------------------------------------
-- Cada archivo .pt desplegado queda registrado: así cada predicción
-- sabe con qué versión del modelo se hizo.
CREATE TABLE modelo_ia (
    id                INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    nombre            VARCHAR(80)  NOT NULL,                   -- 'yolo-gondolas'
    version           VARCHAR(30)  NOT NULL,                   -- 'v1.0.0'
    ruta_pesos        VARCHAR(255) NOT NULL,                   -- 'models/best.pt'
    sha256_pesos      CHAR(64),
    umbral_confianza  NUMERIC(4,3) NOT NULL DEFAULT 0.250 CHECK (umbral_confianza BETWEEN 0 AND 1),
    clases            JSONB,                                   -- {"0": "vacio", "1": "producto"}
    map50             NUMERIC(5,4),                            -- métrica de validación
    activo            BOOLEAN      NOT NULL DEFAULT FALSE,
    cargado_en        TIMESTAMPTZ  NOT NULL DEFAULT now(),
    UNIQUE (nombre, version)
);
-- Solo un modelo activo a la vez
CREATE UNIQUE INDEX ux_modelo_ia_un_activo ON modelo_ia (activo) WHERE activo;

-- Una foto recibida (de cámara o del celular de un reponedor).
-- El archivo vive en la carpeta del recinto; aquí va su ruta.
CREATE TABLE imagen (
    id             BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    recinto_id     INTEGER        NOT NULL REFERENCES recinto(id),
    gondola_id     INTEGER,
    camara_id      INTEGER,
    subida_por     INTEGER        REFERENCES usuario(id),     -- reponedor (si origen = MOVIL)
    origen         origen_imagen  NOT NULL,
    ruta_archivo   VARCHAR(255)   NOT NULL UNIQUE,            -- 'recintos/R01/2026/11/14/R01-CAM03_183000.jpg'
    sha256         CHAR(64),
    ancho_px       INTEGER,
    alto_px        INTEGER,
    capturada_en   TIMESTAMPTZ    NOT NULL,
    recibida_en    TIMESTAMPTZ    NOT NULL DEFAULT now(),
    estado         estado_procesamiento NOT NULL DEFAULT 'PENDIENTE',
    error_detalle  TEXT,
    FOREIGN KEY (gondola_id, recinto_id) REFERENCES gondola (id, recinto_id),
    FOREIGN KEY (camara_id,  recinto_id) REFERENCES camara  (id, recinto_id),
    CONSTRAINT ck_imagen_origen CHECK (
        (origen = 'CAMARA' AND camara_id  IS NOT NULL) OR
        (origen = 'MOVIL'  AND subida_por IS NOT NULL)
    )
);
CREATE INDEX ix_imagen_recinto_fecha ON imagen (recinto_id, capturada_en DESC);
CREATE INDEX ix_imagen_gondola_fecha ON imagen (gondola_id, capturada_en DESC);
CREATE INDEX ix_imagen_pendiente     ON imagen (recibida_en) WHERE estado = 'PENDIENTE';

-- Resultado de pasar una imagen por el modelo.
-- porcentaje_vacio lo calcula el worker (p. ej. área de cajas "vacio"
-- sobre área total de góndola). umbral_aplicado copia el umbral del
-- recinto en ese momento, para que el histórico no cambie si se edita.
CREATE TABLE prediccion (
    id                    BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    imagen_id             BIGINT       NOT NULL REFERENCES imagen(id) ON DELETE CASCADE,
    modelo_id             INTEGER      NOT NULL REFERENCES modelo_ia(id),
    porcentaje_vacio      NUMERIC(5,2) NOT NULL CHECK (porcentaje_vacio BETWEEN 0 AND 100),
    umbral_aplicado       NUMERIC(5,2) NOT NULL,
    supera_umbral         BOOLEAN GENERATED ALWAYS AS (porcentaje_vacio > umbral_aplicado) STORED,
    num_vacios            INTEGER      NOT NULL DEFAULT 0,
    num_productos         INTEGER      NOT NULL DEFAULT 0,
    tiempo_inferencia_ms  INTEGER,
    ruta_imagen_anotada   VARCHAR(255),                        -- copia con las cajas dibujadas
    creada_en             TIMESTAMPTZ  NOT NULL DEFAULT now(),
    UNIQUE (imagen_id, modelo_id)                              -- reprocesar con otro modelo = otra fila
);
CREATE INDEX ix_prediccion_supera ON prediccion (creada_en DESC) WHERE supera_umbral;

-- Cada caja (bounding box) que devolvió YOLO. Coordenadas normalizadas 0..1.
CREATE TABLE deteccion (
    id             BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    prediccion_id  BIGINT       NOT NULL REFERENCES prediccion(id) ON DELETE CASCADE,
    clase          VARCHAR(40)  NOT NULL,                      -- 'vacio' | 'producto'
    confianza      NUMERIC(4,3) NOT NULL CHECK (confianza BETWEEN 0 AND 1),
    x_min REAL NOT NULL, y_min REAL NOT NULL,
    x_max REAL NOT NULL, y_max REAL NOT NULL,
    CHECK (x_min >= 0 AND y_min >= 0 AND x_max <= 1 AND y_max <= 1),
    CHECK (x_min < x_max AND y_min < y_max)
);
CREATE INDEX ix_deteccion_prediccion ON deteccion (prediccion_id);

-- ---------------------------------------------------------------------
-- 4. Tickets
-- ---------------------------------------------------------------------
CREATE SEQUENCE ticket_numero_seq START 1;

CREATE TABLE ticket (
    id                  BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    numero              VARCHAR(12)  NOT NULL UNIQUE
                        DEFAULT ('INC' || lpad(nextval('ticket_numero_seq')::text, 6, '0')),  -- INC000001
    titulo              VARCHAR(150) NOT NULL,
    descripcion         TEXT,
    estado              estado_ticket    NOT NULL DEFAULT 'ABIERTO',
    prioridad           prioridad_ticket NOT NULL DEFAULT 'MEDIA',
    origen              origen_ticket    NOT NULL,
    recinto_id          INTEGER      NOT NULL REFERENCES recinto(id),
    gondola_id          INTEGER,
    porcentaje_vacio    NUMERIC(5,2) CHECK (porcentaje_vacio BETWEEN 0 AND 100),   -- última lectura
    producto_faltante   VARCHAR(150),                          -- lo llena la IA o el reponedor
    categoria_producto  VARCHAR(80),
    enriquecido_ia      BOOLEAN      NOT NULL DEFAULT FALSE,
    creado_por          INTEGER      REFERENCES usuario(id),   -- NULL = generado por el sistema
    asignado_a          INTEGER      REFERENCES usuario(id),   -- reponedor responsable
    asignado_por        INTEGER      REFERENCES usuario(id),   -- supervisor que asignó
    cerrado_por         INTEGER      REFERENCES usuario(id),
    creado_en           TIMESTAMPTZ  NOT NULL DEFAULT now(),
    asignado_en         TIMESTAMPTZ,
    cerrado_en          TIMESTAMPTZ,
    actualizado_en      TIMESTAMPTZ  NOT NULL DEFAULT now(),
    FOREIGN KEY (gondola_id, recinto_id) REFERENCES gondola (id, recinto_id),
    CONSTRAINT ck_ticket_asignado CHECK (estado IN ('ABIERTO', 'CANCELADO') OR asignado_a IS NOT NULL),
    CONSTRAINT ck_ticket_cerrado  CHECK (estado <> 'CERRADO' OR cerrado_en IS NOT NULL)
);
ALTER SEQUENCE ticket_numero_seq OWNED BY ticket.numero;

CREATE INDEX ix_ticket_recinto_estado ON ticket (recinto_id, estado, creado_en DESC);
CREATE INDEX ix_ticket_asignado       ON ticket (asignado_a, estado) WHERE asignado_a IS NOT NULL;
-- Evita duplicados: como máximo un ticket de cámara abierto por góndola.
-- Las fotos siguientes se agregan como evidencia SEGUIMIENTO.
CREATE UNIQUE INDEX ux_ticket_camara_abierto_por_gondola
    ON ticket (gondola_id)
    WHERE origen = 'CAMARA' AND estado IN ('ABIERTO', 'ASIGNADO', 'EN_PROGRESO');

-- Fotos asociadas a un ticket: la que lo abrió, las de seguimiento y
-- la de cierre (que el reponedor toma después de reponer).
CREATE TABLE ticket_imagen (
    ticket_id    BIGINT         NOT NULL REFERENCES ticket(id) ON DELETE CASCADE,
    imagen_id    BIGINT         NOT NULL REFERENCES imagen(id),
    tipo         tipo_evidencia NOT NULL,
    agregada_en  TIMESTAMPTZ    NOT NULL DEFAULT now(),
    PRIMARY KEY (ticket_id, imagen_id)
);
CREATE INDEX ix_ticket_imagen_imagen ON ticket_imagen (imagen_id);

CREATE TABLE comentario (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    ticket_id   BIGINT      NOT NULL REFERENCES ticket(id) ON DELETE CASCADE,
    usuario_id  INTEGER     NOT NULL REFERENCES usuario(id),
    texto       TEXT        NOT NULL CHECK (length(btrim(texto)) > 0),
    creado_en   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ix_comentario_ticket ON comentario (ticket_id, creado_en);

-- Auditoría: se llena sola por trigger en cada cambio de estado o asignación.
CREATE TABLE historial_ticket (
    id                 BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    ticket_id          BIGINT        NOT NULL REFERENCES ticket(id) ON DELETE CASCADE,
    usuario_id         INTEGER       REFERENCES usuario(id),   -- NULL = sistema
    estado_anterior    estado_ticket,
    estado_nuevo       estado_ticket NOT NULL,
    asignado_anterior  INTEGER       REFERENCES usuario(id),
    asignado_nuevo     INTEGER       REFERENCES usuario(id),
    creado_en          TIMESTAMPTZ   NOT NULL DEFAULT now()
);
CREATE INDEX ix_historial_ticket ON historial_ticket (ticket_id, creado_en);

-- Respuesta de la API de IA (LLM con visión) que identifica qué producto
-- falta. Se guarda la respuesta completa para auditar costo y calidad.
CREATE TABLE analisis_ia (
    id                   BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    ticket_id            BIGINT       NOT NULL REFERENCES ticket(id) ON DELETE CASCADE,
    imagen_id            BIGINT       NOT NULL REFERENCES imagen(id),
    proveedor            VARCHAR(40)  NOT NULL,                -- proveedor de la API
    modelo               VARCHAR(80)  NOT NULL,
    productos_faltantes  JSONB        NOT NULL DEFAULT '[]',   -- [{"producto": "...", "confianza": 0.8}]
    resumen              TEXT,
    tokens_entrada       INTEGER,
    tokens_salida        INTEGER,
    latencia_ms          INTEGER,
    exitoso              BOOLEAN      NOT NULL DEFAULT TRUE,
    error_detalle        TEXT,
    creado_en            TIMESTAMPTZ  NOT NULL DEFAULT now()
);
CREATE INDEX ix_analisis_ia_ticket ON analisis_ia (ticket_id);

CREATE TABLE notificacion (
    id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    usuario_id    INTEGER           NOT NULL REFERENCES usuario(id) ON DELETE CASCADE,
    ticket_id     BIGINT            REFERENCES ticket(id) ON DELETE CASCADE,
    tipo          tipo_notificacion NOT NULL,
    mensaje       VARCHAR(255)      NOT NULL,
    leida         BOOLEAN           NOT NULL DEFAULT FALSE,
    enviada_push  BOOLEAN           NOT NULL DEFAULT FALSE,    -- el worker la marca al enviar por FCM
    creada_en     TIMESTAMPTZ       NOT NULL DEFAULT now()
);
CREATE INDEX ix_notificacion_no_leida ON notificacion (usuario_id, creada_en DESC) WHERE NOT leida;
CREATE INDEX ix_notificacion_push_pendiente ON notificacion (creada_en) WHERE NOT enviada_push;

-- ---------------------------------------------------------------------
-- 5. Funciones y triggers
-- ---------------------------------------------------------------------
-- Usuario de la transacción actual (lo fija el backend con SET LOCAL).
CREATE FUNCTION app_usuario_actual() RETURNS INTEGER
LANGUAGE sql STABLE AS $$
    SELECT NULLIF(current_setting('app.usuario_id', true), '')::INTEGER
$$;

CREATE FUNCTION fn_prioridad_por_vacio(p_porcentaje NUMERIC) RETURNS prioridad_ticket
LANGUAGE sql IMMUTABLE AS $$
    SELECT CASE
        WHEN p_porcentaje >= 40 THEN 'CRITICA'::prioridad_ticket
        WHEN p_porcentaje >= 20 THEN 'ALTA'
        WHEN p_porcentaje >= 10 THEN 'MEDIA'
        ELSE 'BAJA'
    END
$$;

CREATE FUNCTION fn_set_actualizado_en() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    NEW.actualizado_en := now();
    RETURN NEW;
END $$;

CREATE TRIGGER trg_usuario_actualizado
    BEFORE UPDATE ON usuario
    FOR EACH ROW EXECUTE FUNCTION fn_set_actualizado_en();

-- Reglas de negocio del ticket antes de guardar:
--  * solo se asigna a un REPONEDOR activo del mismo recinto
--  * al asignar, ABIERTO pasa a ASIGNADO y se registra quién/cuándo
--  * al cerrar se marca cerrado_en; al reabrir se limpia
CREATE FUNCTION fn_ticket_reglas() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.asignado_a IS NOT NULL
       AND (TG_OP = 'INSERT' OR NEW.asignado_a IS DISTINCT FROM OLD.asignado_a) THEN

        IF NOT EXISTS (
            SELECT 1
            FROM usuario u
            JOIN usuario_recinto ur ON ur.usuario_id = u.id
            WHERE u.id = NEW.asignado_a
              AND u.rol = 'REPONEDOR'
              AND u.activo
              AND ur.recinto_id = NEW.recinto_id
        ) THEN
            RAISE EXCEPTION 'El usuario % no es un reponedor activo del recinto %',
                            NEW.asignado_a, NEW.recinto_id
                  USING ERRCODE = 'check_violation';
        END IF;

        NEW.asignado_en  := now();
        NEW.asignado_por := COALESCE(app_usuario_actual(), NEW.asignado_por);
        IF NEW.estado = 'ABIERTO' THEN
            NEW.estado := 'ASIGNADO';
        END IF;
    END IF;

    IF NEW.estado = 'CERRADO' THEN
        IF TG_OP = 'INSERT' OR OLD.estado <> 'CERRADO' THEN
            NEW.cerrado_en  := COALESCE(NEW.cerrado_en, now());
            NEW.cerrado_por := COALESCE(NEW.cerrado_por, app_usuario_actual());
        END IF;
    ELSE
        NEW.cerrado_en  := NULL;
        NEW.cerrado_por := NULL;
    END IF;

    IF TG_OP = 'UPDATE' THEN
        NEW.actualizado_en := now();
    END IF;
    RETURN NEW;
END $$;

CREATE TRIGGER trg_ticket_reglas
    BEFORE INSERT OR UPDATE ON ticket
    FOR EACH ROW EXECUTE FUNCTION fn_ticket_reglas();

-- Después de guardar: historial + notificación al reponedor asignado.
CREATE FUNCTION fn_ticket_historial() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    v_usuario INTEGER := app_usuario_actual();
BEGIN
    IF TG_OP = 'INSERT' THEN
        INSERT INTO historial_ticket (ticket_id, usuario_id, estado_anterior, estado_nuevo,
                                      asignado_anterior, asignado_nuevo)
        VALUES (NEW.id, v_usuario, NULL, NEW.estado, NULL, NEW.asignado_a);
    ELSIF NEW.estado IS DISTINCT FROM OLD.estado
       OR NEW.asignado_a IS DISTINCT FROM OLD.asignado_a THEN
        INSERT INTO historial_ticket (ticket_id, usuario_id, estado_anterior, estado_nuevo,
                                      asignado_anterior, asignado_nuevo)
        VALUES (NEW.id, v_usuario, OLD.estado, NEW.estado, OLD.asignado_a, NEW.asignado_a);
    END IF;

    IF NEW.asignado_a IS NOT NULL
       AND NEW.asignado_a IS DISTINCT FROM v_usuario
       AND (TG_OP = 'INSERT' OR NEW.asignado_a IS DISTINCT FROM OLD.asignado_a) THEN
        INSERT INTO notificacion (usuario_id, ticket_id, tipo, mensaje)
        VALUES (NEW.asignado_a, NEW.id, 'TICKET_ASIGNADO',
                format('Se te asignó %s: %s', NEW.numero, NEW.titulo));
    END IF;
    RETURN NULL;
END $$;

CREATE TRIGGER trg_ticket_historial
    AFTER INSERT OR UPDATE ON ticket
    FOR EACH ROW EXECUTE FUNCTION fn_ticket_historial();

-- ---------------------------------------------------------------------
-- 6. Regla principal: de predicción a ticket
-- ---------------------------------------------------------------------
-- El worker de inferencia la llama justo después de guardar una
-- predicción. Devuelve el id del ticket creado o actualizado, o NULL
-- si el % de vacío no supera el umbral.
--   * Cámara: si la góndola ya tiene un ticket de cámara abierto, la
--     foto se agrega como SEGUIMIENTO y se actualiza el %; si no, se
--     abre un ticket genérico y se avisa a los supervisores del recinto.
--   * Móvil: se abre un ticket a nombre del reponedor que tomó la foto
--     (queda asignado a él; el supervisor puede reasignarlo).
CREATE FUNCTION fn_ticket_desde_prediccion(p_prediccion_id BIGINT) RETURNS BIGINT
LANGUAGE plpgsql AS $$
DECLARE
    p          prediccion%ROWTYPE;
    i          imagen%ROWTYPE;
    g          gondola%ROWTYPE;
    v_ticket   BIGINT;
    v_lugar    TEXT;
BEGIN
    SELECT * INTO STRICT p FROM prediccion WHERE id = p_prediccion_id;
    IF NOT p.supera_umbral THEN
        RETURN NULL;
    END IF;

    SELECT * INTO STRICT i FROM imagen WHERE id = p.imagen_id;
    SELECT * INTO g FROM gondola WHERE id = i.gondola_id;
    v_lugar := COALESCE(g.codigo || COALESCE(' · ' || g.categoria, ''), 'góndola sin identificar');

    -- ¿Ya hay un ticket de cámara abierto para esta góndola?
    IF i.origen = 'CAMARA' AND i.gondola_id IS NOT NULL THEN
        SELECT id INTO v_ticket
        FROM ticket
        WHERE gondola_id = i.gondola_id
          AND origen = 'CAMARA'
          AND estado IN ('ABIERTO', 'ASIGNADO', 'EN_PROGRESO')
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

    INSERT INTO ticket (titulo, descripcion, prioridad, origen, recinto_id, gondola_id,
                        porcentaje_vacio, creado_por, asignado_a)
    VALUES (
        format('Vacío detectado en %s', v_lugar),
        format('Ticket generado automáticamente desde %s. El modelo detectó %s%% de vacío (umbral %s%%).',
               CASE i.origen WHEN 'CAMARA' THEN 'cámara' ELSE 'foto móvil' END,
               p.porcentaje_vacio, p.umbral_aplicado),
        fn_prioridad_por_vacio(p.porcentaje_vacio),
        i.origen::TEXT::origen_ticket,
        i.recinto_id,
        i.gondola_id,
        p.porcentaje_vacio,
        i.subida_por,                                         -- NULL si vino de cámara
        CASE WHEN i.origen = 'MOVIL' THEN i.subida_por END
    )
    RETURNING id INTO v_ticket;

    INSERT INTO ticket_imagen (ticket_id, imagen_id, tipo)
    VALUES (v_ticket, i.id, 'APERTURA');

    -- Alerta a todos los supervisores activos del recinto
    INSERT INTO notificacion (usuario_id, ticket_id, tipo, mensaje)
    SELECT u.id, v_ticket, 'ALERTA_VACIO',
           format('%s%% de vacío en %s', p.porcentaje_vacio, v_lugar)
    FROM usuario u
    JOIN usuario_recinto ur ON ur.usuario_id = u.id
    WHERE ur.recinto_id = i.recinto_id
      AND u.rol = 'SUPERVISOR'
      AND u.activo;

    RETURN v_ticket;
END $$;

-- ---------------------------------------------------------------------
-- 7. Vistas para las pantallas
-- ---------------------------------------------------------------------
-- Bandeja de tickets (panel del supervisor y lista del reponedor)
CREATE VIEW v_ticket_resumen AS
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
    ) AS cierre_verificado
FROM ticket t
JOIN recinto r       ON r.id  = t.recinto_id
LEFT JOIN gondola g  ON g.id  = t.gondola_id
LEFT JOIN usuario ua ON ua.id = t.asignado_a
LEFT JOIN usuario uc ON uc.id = t.creado_por;

-- Carga de trabajo de cada reponedor (lo que ve el supervisor)
CREATE VIEW v_carga_reponedor AS
SELECT
    ur.recinto_id,
    u.id AS usuario_id,
    u.nombre || ' ' || u.apellido AS reponedor,
    count(t.id) FILTER (WHERE t.estado = 'ASIGNADO')    AS asignados,
    count(t.id) FILTER (WHERE t.estado = 'EN_PROGRESO') AS en_progreso,
    count(t.id) FILTER (
        WHERE t.estado = 'CERRADO'
          AND (t.cerrado_en AT TIME ZONE 'America/Santiago')::DATE
              = (now() AT TIME ZONE 'America/Santiago')::DATE
    ) AS cerrados_hoy
FROM usuario u
JOIN usuario_recinto ur ON ur.usuario_id = u.id
LEFT JOIN ticket t ON t.asignado_a = u.id AND t.recinto_id = ur.recinto_id
WHERE u.rol = 'REPONEDOR' AND u.activo
GROUP BY ur.recinto_id, u.id, u.nombre, u.apellido;

COMMIT;
