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
