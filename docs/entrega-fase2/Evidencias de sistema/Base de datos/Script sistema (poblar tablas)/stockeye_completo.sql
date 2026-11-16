-- =====================================================================
--  StockEye · Script completo: crea el esquema y carga los datos de demo
--  Uso:  createdb stockeye && psql -d stockeye -v ON_ERROR_STOP=1 -f stockeye_completo.sql
--  Une, en orden, 001_esquema, 002_produccion, 003_carga_de_fotos, 004_categorias y seed_demo.
-- =====================================================================

-- >>>>> 001_esquema.sql
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

-- >>>>> 002_produccion.sql
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

-- >>>>> 003_carga_de_fotos.sql
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

-- >>>>> 004_categorias.sql
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

-- >>>>> seed_demo.sql
-- =====================================================================
--  StockEye · Datos de demostración (2 recintos, 8 usuarios, tickets)
--  Ejecutar después de schema.sql:   psql -d stockeye -f seed_demo.sql
--  Se ejecuta con:   python -m stockeye.cli db seed   (o desde DBeaver)
--  SOLO DESARROLLO / DEMO. Todos los usuarios tienen la clave  StockEye2026!
--  Las cámaras tienen la API key  demo-<código>  (ej. demo-R01-CAM03).
-- =====================================================================

BEGIN;

-- Recintos ------------------------------------------------------------
INSERT INTO recinto (codigo, nombre, direccion, comuna, carpeta_imagenes, umbral_vacio) VALUES
    ('R01', 'Recinto 1 · Providencia', 'Av. Ejemplo 1234', 'Providencia', 'recintos/R01', 5.00),
    ('R02', 'Recinto 2 · Ñuñoa',       'Calle Demo 567',   'Ñuñoa',       'recintos/R02', 5.00);

-- Usuarios ------------------------------------------------------------
INSERT INTO usuario (rut, nombre, apellido, email, password_hash, rol) VALUES
    ('11111111-1', 'Andrea',   'Pizarro',   'admin@stockeye.test',     '$2b$12$P8cJPGN7d1EN8e2yvonC4Ogp86SIvPCCp3RZ1E0MS9yjioaWRnCnK', 'ADMINISTRADOR'),
    ('22222222-2', 'Carolina', 'Muñoz',     'cmunoz@stockeye.test',    '$2b$12$P8cJPGN7d1EN8e2yvonC4Ogp86SIvPCCp3RZ1E0MS9yjioaWRnCnK', 'SUPERVISOR'),
    ('33333333-3', 'Pablo',    'Contreras', 'pcontreras@stockeye.test','$2b$12$P8cJPGN7d1EN8e2yvonC4Ogp86SIvPCCp3RZ1E0MS9yjioaWRnCnK', 'SUPERVISOR'),
    ('44444444-4', 'Diego',    'Soto',      'dsoto@stockeye.test',     '$2b$12$P8cJPGN7d1EN8e2yvonC4Ogp86SIvPCCp3RZ1E0MS9yjioaWRnCnK', 'REPONEDOR'),
    ('55555555-5', 'Javiera',  'Rojas',     'jrojas@stockeye.test',    '$2b$12$P8cJPGN7d1EN8e2yvonC4Ogp86SIvPCCp3RZ1E0MS9yjioaWRnCnK', 'REPONEDOR'),
    ('66666666-6', 'Matías',   'Fuentes',   'mfuentes@stockeye.test',  '$2b$12$P8cJPGN7d1EN8e2yvonC4Ogp86SIvPCCp3RZ1E0MS9yjioaWRnCnK', 'REPONEDOR'),
    ('77777777-7', 'Camila',   'Vera',      'cvera@stockeye.test',     '$2b$12$P8cJPGN7d1EN8e2yvonC4Ogp86SIvPCCp3RZ1E0MS9yjioaWRnCnK', 'REPONEDOR'),
    ('88888888-8', 'Tomás',    'Herrera',   'therrera@stockeye.test',  '$2b$12$P8cJPGN7d1EN8e2yvonC4Ogp86SIvPCCp3RZ1E0MS9yjioaWRnCnK', 'REPONEDOR');

INSERT INTO usuario_recinto (usuario_id, recinto_id)
SELECT u.id, r.id
FROM (VALUES
        ('cmunoz@stockeye.test',     'R01'),
        ('dsoto@stockeye.test',      'R01'),
        ('jrojas@stockeye.test',     'R01'),
        ('mfuentes@stockeye.test',   'R01'),
        ('pcontreras@stockeye.test', 'R02'),
        ('cvera@stockeye.test',      'R02'),
        ('therrera@stockeye.test',   'R02')
     ) AS x(email, recinto)
JOIN usuario u ON u.email = x.email
JOIN recinto r ON r.codigo = x.recinto;

-- Góndolas y cámaras ---------------------------------------------------
INSERT INTO gondola (recinto_id, codigo, pasillo, categoria)
SELECT r.id, x.codigo, x.pasillo, x.categoria
FROM (VALUES
        ('R01', 'P01-G01', '1', 'Lácteos'),
        ('R01', 'P03-G02', '3', 'Bebidas'),
        ('R01', 'P04-G01', '4', 'Abarrotes'),
        ('R01', 'P05-G03', '5', 'Limpieza'),
        ('R01', 'P07-G02', '7', 'Snacks'),
        ('R02', 'P02-G01', '2', 'Panadería'),
        ('R02', 'P03-G01', '3', 'Bebidas'),
        ('R02', 'P06-G04', '6', 'Conservas')
     ) AS x(recinto, codigo, pasillo, categoria)
JOIN recinto r ON r.codigo = x.recinto;

INSERT INTO camara (recinto_id, gondola_id, codigo, nombre, api_key_hash)
SELECT g.recinto_id, g.id, x.cam, 'Cámara ' || x.cam,
       'sha256$' || encode(sha256(convert_to('demo-' || x.cam, 'UTF8')), 'hex')
FROM (VALUES
        ('R01-CAM01', 'R01', 'P01-G01'),
        ('R01-CAM02', 'R01', 'P03-G02'),
        ('R01-CAM03', 'R01', 'P04-G01'),
        ('R01-CAM04', 'R01', 'P05-G03'),
        ('R01-CAM05', 'R01', 'P07-G02'),
        ('R02-CAM01', 'R02', 'P02-G01'),
        ('R02-CAM02', 'R02', 'P06-G04'),
        ('R02-CAM03', 'R02', 'P03-G01')
     ) AS x(cam, recinto, gondola)
JOIN recinto r ON r.codigo = x.recinto
JOIN gondola g ON g.recinto_id = r.id AND g.codigo = x.gondola;

-- Modelo YOLO activo ----------------------------------------------------
-- Igual al que genera herramientas/empaquetar_modelo.py con best.pt (SegFormer mit-b1).
-- "python -m stockeye.cli modelo registrar" lo actualiza con el sha256 y el benchmark reales.
INSERT INTO modelo_ia (nombre, version, ruta_pesos, umbral_confianza, clases, familia, parametros, metricas,
                       activo, activado_en)
VALUES ('segformer-mit-b1', 'v1', 'modelos/segformer-mit-b1-v1.onnx', 0.500,
        '{"0": "fondo", "1": "ocupado", "2": "vacio"}', 'SEGFORMER',
        '{"lado": 1280, "pixeles_max": 740000, "hilos_recomendados": 2, "modo": "completa"}',
        '{"iou_vacio": 0.3544, "iou_gondola": 0.8181, "epoca": 19}', TRUE, now());

-- Helpers temporales (solo existen durante esta sesión) -----------------
-- Simulan lo que hará el worker: guardar imagen + predicción y llamar
-- a fn_ticket_desde_prediccion().
CREATE FUNCTION pg_temp.demo_foto_camara(p_camara TEXT, p_pct NUMERIC, p_min_atras INT)
RETURNS BIGINT LANGUAGE plpgsql AS $$
DECLARE
    c camara%ROWTYPE;
    v_img BIGINT;
    v_pred BIGINT;
    v_umbral NUMERIC;
    v_ts TIMESTAMPTZ := now() - make_interval(mins => p_min_atras);
BEGIN
    PERFORM set_config('app.usuario_id', '', true);            -- las cámaras actúan como "sistema"
    SELECT * INTO STRICT c FROM camara WHERE codigo = p_camara;
    SELECT umbral_vacio INTO v_umbral FROM recinto WHERE id = c.recinto_id;

    INSERT INTO imagen (recinto_id, gondola_id, camara_id, origen, ruta_archivo,
                        capturada_en, estado, ancho_px, alto_px)
    SELECT c.recinto_id, c.gondola_id, c.id, 'CAMARA',
           format('%s/%s/%s_%s.jpg', r.carpeta_imagenes,
                  to_char(v_ts AT TIME ZONE 'America/Santiago', 'YYYY/MM/DD'),
                  c.codigo, to_char(v_ts AT TIME ZONE 'America/Santiago', 'HH24MISS')),
           v_ts, 'PROCESADA', 1920, 1080
    FROM recinto r WHERE r.id = c.recinto_id
    RETURNING id INTO v_img;

    INSERT INTO prediccion (imagen_id, modelo_id, porcentaje_vacio, umbral_aplicado,
                            num_vacios, num_productos, tiempo_inferencia_ms,
                            ruta_imagen_anotada)
    SELECT v_img, m.id, p_pct, v_umbral,
           GREATEST(1, round(p_pct / 4)::INT), 60 - round(p_pct / 2)::INT, 85,
           replace((SELECT ruta_archivo FROM imagen WHERE id = v_img), '.jpg', '_pred.jpg')
    FROM modelo_ia m WHERE m.activo
    RETURNING id INTO v_pred;

    INSERT INTO deteccion (prediccion_id, clase, confianza, x_min, y_min, x_max, y_max) VALUES
        (v_pred, 'vacio',    0.91, 0.12, 0.30, 0.27, 0.52),
        (v_pred, 'producto', 0.88, 0.30, 0.30, 0.45, 0.52);

    RETURN fn_ticket_desde_prediccion(v_pred);
END $$;

CREATE FUNCTION pg_temp.demo_foto_movil(p_email TEXT, p_gondola TEXT, p_pct NUMERIC, p_min_atras INT)
RETURNS BIGINT LANGUAGE plpgsql AS $$
DECLARE
    u usuario%ROWTYPE;
    g gondola%ROWTYPE;
    v_img BIGINT;
    v_pred BIGINT;
    v_ts TIMESTAMPTZ := now() - make_interval(mins => p_min_atras);
BEGIN
    SELECT * INTO STRICT u FROM usuario WHERE email = p_email;
    SELECT g2.* INTO STRICT g FROM gondola g2
      JOIN usuario_recinto ur ON ur.recinto_id = g2.recinto_id AND ur.usuario_id = u.id
     WHERE g2.codigo = p_gondola;

    INSERT INTO imagen (recinto_id, gondola_id, subida_por, origen, ruta_archivo, capturada_en, estado)
    SELECT g.recinto_id, g.id, u.id, 'MOVIL',
           format('%s/%s/movil_u%s_%s.jpg', r.carpeta_imagenes,
                  to_char(v_ts AT TIME ZONE 'America/Santiago', 'YYYY/MM/DD'),
                  u.id, to_char(v_ts AT TIME ZONE 'America/Santiago', 'HH24MISS')),
           v_ts, 'PROCESADA'
    FROM recinto r WHERE r.id = g.recinto_id
    RETURNING id INTO v_img;

    INSERT INTO prediccion (imagen_id, modelo_id, porcentaje_vacio, umbral_aplicado, tiempo_inferencia_ms)
    SELECT v_img, m.id, p_pct, r.umbral_vacio, 90
    FROM modelo_ia m, recinto r
    WHERE m.activo AND r.id = g.recinto_id
    RETURNING id INTO v_pred;

    PERFORM set_config('app.usuario_id', u.id::TEXT, true);
    RETURN COALESCE(fn_ticket_desde_prediccion(v_pred), -v_img);   -- negativo = no generó ticket
END $$;

-- Escenario -----------------------------------------------------------
-- R01: tres alertas de cámara, una lectura bajo el umbral, una foto móvil
SELECT pg_temp.demo_foto_camara('R01-CAM03', 18.40, 95);   -- INC000001 Abarrotes
SELECT pg_temp.demo_foto_camara('R01-CAM01', 31.75, 70);   -- INC000002 Lácteos
SELECT pg_temp.demo_foto_camara('R01-CAM02',  7.20, 40);   -- INC000003 Bebidas
SELECT pg_temp.demo_foto_camara('R01-CAM04',  3.10, 35);   -- sin ticket (bajo 5 %)
SELECT pg_temp.demo_foto_camara('R01-CAM03', 22.10, 20);   -- seguimiento de INC000001
SELECT pg_temp.demo_foto_movil('mfuentes@stockeye.test', 'P07-G02', 12.50, 60);  -- INC000004 Snacks
-- R02: alerta crítica sin asignar
SELECT pg_temp.demo_foto_camara('R02-CAM02', 45.00, 15);   -- INC000005 Conservas

-- Que creado_en coincida con la foto de apertura (solo para la demo)
UPDATE ticket t
   SET creado_en = i.capturada_en
  FROM ticket_imagen ti
  JOIN imagen i ON i.id = ti.imagen_id
 WHERE ti.ticket_id = t.id AND ti.tipo = 'APERTURA';
UPDATE historial_ticket h
   SET creado_en = t.creado_en
  FROM ticket t
 WHERE h.ticket_id = t.id AND h.estado_anterior IS NULL;

-- La supervisora del R01 asigna tickets
SELECT set_config('app.usuario_id', (SELECT id::TEXT FROM usuario WHERE email = 'cmunoz@stockeye.test'), true);
UPDATE ticket SET asignado_a = (SELECT id FROM usuario WHERE email = 'dsoto@stockeye.test')
 WHERE numero = 'INC000001';
UPDATE ticket SET asignado_a = (SELECT id FROM usuario WHERE email = 'jrojas@stockeye.test')
 WHERE numero = 'INC000002';
-- El ticket que reportó Matías desde la app también llega sin asignar; la supervisora se lo asigna
UPDATE ticket SET asignado_a = (SELECT id FROM usuario WHERE email = 'mfuentes@stockeye.test')
 WHERE numero = 'INC000004';
INSERT INTO comentario (ticket_id, usuario_id, texto)
SELECT t.id, u.id, 'Revisar bodega: ayer llegó reposición de arroz.'
FROM ticket t, usuario u
WHERE t.numero = 'INC000001' AND u.email = 'cmunoz@stockeye.test';

-- La API de IA identificó el producto faltante del INC000001
INSERT INTO analisis_ia (ticket_id, imagen_id, proveedor, modelo, productos_faltantes, resumen,
                         tokens_entrada, tokens_salida, latencia_ms)
SELECT t.id, ti.imagen_id, 'proveedor-llm', 'modelo-vision',
       '[{"producto": "Arroz grado 1, 1 kg", "confianza": 0.86},
         {"producto": "Fideos spaghetti 400 g", "confianza": 0.41}]',
       'Faltan principalmente bolsas de arroz de 1 kg en la repisa central.',
       1450, 120, 2300
FROM ticket t JOIN ticket_imagen ti ON ti.ticket_id = t.id AND ti.tipo = 'APERTURA'
WHERE t.numero = 'INC000001';
UPDATE ticket SET producto_faltante = 'Arroz grado 1, 1 kg',
                  categoria_producto = 'Abarrotes',
                  enriquecido_ia = TRUE
 WHERE numero = 'INC000001';

-- Diego empieza a trabajar el INC000001
SELECT set_config('app.usuario_id', (SELECT id::TEXT FROM usuario WHERE email = 'dsoto@stockeye.test'), true);
UPDATE ticket SET estado = 'EN_PROGRESO' WHERE numero = 'INC000001';
INSERT INTO comentario (ticket_id, usuario_id, texto)
SELECT t.id, u.id, 'Voy con 2 cajas desde bodega.'
FROM ticket t, usuario u
WHERE t.numero = 'INC000001' AND u.email = 'dsoto@stockeye.test';

-- Matías repone y cierra su ticket con foto de verificación (1,8 %)
SELECT set_config('app.usuario_id', (SELECT id::TEXT FROM usuario WHERE email = 'mfuentes@stockeye.test'), true);
UPDATE ticket SET producto_faltante = 'Papas fritas corte americano 250 g',
                  categoria_producto = 'Snacks'
 WHERE numero = 'INC000004';
WITH foto AS (
    SELECT pg_temp.demo_foto_movil('mfuentes@stockeye.test', 'P07-G02', 1.80, 5) AS r
)
INSERT INTO ticket_imagen (ticket_id, imagen_id, tipo)
SELECT t.id, -foto.r, 'CIERRE'
FROM foto, ticket t
WHERE t.numero = 'INC000004';
SELECT set_config('app.usuario_id', (SELECT id::TEXT FROM usuario WHERE email = 'mfuentes@stockeye.test'), true);
UPDATE ticket SET estado = 'CERRADO' WHERE numero = 'INC000004';
INSERT INTO comentario (ticket_id, usuario_id, texto)
SELECT t.id, u.id, 'Repuesto completo, quedan 3 cajas en bodega.'
FROM ticket t, usuario u
WHERE t.numero = 'INC000004' AND u.email = 'mfuentes@stockeye.test';

-- Estado de las cámaras para el panel de administración (una sin señal)
UPDATE camara SET ultima_captura = now() - interval '2 minutes';
UPDATE camara SET ultima_captura = now() - interval '2 hours',
                  ultimo_error = 'Sin respuesta RTSP (timeout 10 s)', ultimo_error_en = now() - interval '5 minutes'
 WHERE codigo = 'R02-CAM03';
UPDATE usuario SET ultimo_acceso = now() - (random() * interval '3 hours'),
                   ultimo_acceso_origen = CASE rol WHEN 'REPONEDOR' THEN 'app' ELSE 'web' END;

COMMIT;
