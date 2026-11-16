-- =====================================================================
--  StockEye · pruebas de reglas de la BD (sobre una copia con el seed)
--  psql -d stockeye_test -f db/tests/test_reglas.sql
--  Cada bloque DEBE fallar: si alguno imprime "FALLA:", la regla no se cumple.
-- =====================================================================
\set ON_ERROR_STOP off

\echo '1) Asignar a un reponedor de OTRO recinto → debe fallar'
DO $$ BEGIN
    UPDATE ticket SET asignado_a = (SELECT id FROM usuario WHERE email = 'cvera@stockeye.test')
     WHERE numero = 'INC000003';
    RAISE EXCEPTION 'FALLA: se asignó a una reponedora de R02 un ticket de R01';
EXCEPTION WHEN check_violation THEN RAISE NOTICE 'ok: %', SQLERRM;
END $$;

\echo '2) Asignar a un SUPERVISOR → debe fallar'
DO $$ BEGIN
    UPDATE ticket SET asignado_a = (SELECT id FROM usuario WHERE email = 'cmunoz@stockeye.test')
     WHERE numero = 'INC000003';
    RAISE EXCEPTION 'FALLA: se asignó un ticket a un supervisor';
EXCEPTION WHEN check_violation THEN RAISE NOTICE 'ok: %', SQLERRM;
END $$;

\echo '3) EN_PROGRESO sin responsable → debe fallar'
DO $$ BEGIN
    UPDATE ticket SET estado = 'EN_PROGRESO' WHERE numero = 'INC000003';
    RAISE EXCEPTION 'FALLA: ticket en progreso sin asignado';
EXCEPTION WHEN check_violation THEN RAISE NOTICE 'ok: %', SQLERRM;
END $$;

\echo '4) Segundo ticket de cámara abierto en la misma góndola → debe fallar'
DO $$ BEGIN
    INSERT INTO ticket (titulo, origen, recinto_id, gondola_id)
    SELECT 'duplicado', 'CAMARA', recinto_id, gondola_id FROM ticket WHERE numero = 'INC000001';
    RAISE EXCEPTION 'FALLA: dos tickets de cámara abiertos para la misma góndola';
EXCEPTION WHEN unique_violation THEN RAISE NOTICE 'ok: %', SQLERRM;
END $$;

\echo '5) Imagen con góndola de otro recinto → debe fallar'
DO $$ BEGIN
    INSERT INTO imagen (recinto_id, gondola_id, subida_por, origen, ruta_archivo, capturada_en)
    SELECT 1, g.id, u.id, 'MOVIL', 'recintos/R01/x.jpg', now()
      FROM gondola g, usuario u WHERE g.recinto_id = 2 AND u.email = 'dsoto@stockeye.test' LIMIT 1;
    RAISE EXCEPTION 'FALLA: imagen de R01 con góndola de R02';
EXCEPTION WHEN foreign_key_violation THEN RAISE NOTICE 'ok: %', SQLERRM;
END $$;

\echo '6) Imagen de CAMARA sin cámara → debe fallar'
DO $$ BEGIN
    INSERT INTO imagen (recinto_id, origen, ruta_archivo, capturada_en) VALUES (1, 'CAMARA', 'recintos/R01/y.jpg', now());
    RAISE EXCEPTION 'FALLA: imagen de cámara sin camara_id';
EXCEPTION WHEN check_violation THEN RAISE NOTICE 'ok: %', SQLERRM;
END $$;

\echo '7) Dos modelos activos → debe fallar'
DO $$ BEGIN
    INSERT INTO modelo_ia (nombre, version, ruta_pesos, activo) VALUES ('otro', 'v9', 'modelos/otro.onnx', TRUE);
    RAISE EXCEPTION 'FALLA: dos modelos activos a la vez';
EXCEPTION WHEN unique_violation THEN RAISE NOTICE 'ok: %', SQLERRM;
END $$;

\echo '8) Asignación válida: ABIERTO pasa solo a ASIGNADO y queda en el historial'
BEGIN;
SELECT set_config('app.usuario_id', (SELECT id::TEXT FROM usuario WHERE email = 'cmunoz@stockeye.test'), true);
UPDATE ticket SET asignado_a = (SELECT id FROM usuario WHERE email = 'jrojas@stockeye.test') WHERE numero = 'INC000003';
DO $$ BEGIN
    IF (SELECT estado FROM ticket WHERE numero = 'INC000003') <> 'ASIGNADO' THEN
        RAISE EXCEPTION 'FALLA: el trigger no pasó el ticket a ASIGNADO';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM historial_ticket h JOIN ticket t ON t.id = h.ticket_id
                    WHERE t.numero = 'INC000003' AND h.estado_nuevo = 'ASIGNADO'
                      AND h.usuario_id = (SELECT id FROM usuario WHERE email = 'cmunoz@stockeye.test')) THEN
        RAISE EXCEPTION 'FALLA: el historial no registró quién asignó';
    END IF;
    RAISE NOTICE 'ok: asignado, con historial y notificación';
END $$;
ROLLBACK;
