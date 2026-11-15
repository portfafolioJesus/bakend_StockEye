-- =====================================================================
--  StockEye · Consultas útiles (solo lectura)
--  En DBeaver: Archivo → Abrir archivo… → este archivo, y elige la conexión "stockeye".
--    · Ctrl+Enter  ejecuta la consulta donde está el cursor
--    · Alt+X       ejecuta todo el archivo (cada resultado en una pestaña)
--  Las horas se muestran en hora de Chile (America/Santiago).
--  Donde dice  'INC000001'  o  'R01'  cámbialo por el ticket o recinto que quieras ver.
-- =====================================================================


-- ---------------------------------------------------------------------
-- 1. USUARIOS
-- ---------------------------------------------------------------------

-- 1.1 Todos los usuarios con su rol, recintos y último acceso
SELECT u.id,
       u.nombre || ' ' || u.apellido                                  AS nombre,
       u.email,
       u.rol,
       u.activo,
       COALESCE(string_agg(r.codigo, ', ' ORDER BY r.codigo), CASE WHEN u.rol = 'ADMINISTRADOR' THEN 'Todos' END) AS recintos,
       to_char(u.ultimo_acceso AT TIME ZONE 'America/Santiago', 'DD-MM-YYYY HH24:MI') AS ultimo_acceso,
       u.ultimo_acceso_origen                                         AS desde,
       u.debe_cambiar_clave                                           AS clave_temporal
  FROM usuario u
  LEFT JOIN usuario_recinto ur ON ur.usuario_id = u.id
  LEFT JOIN recinto r          ON r.id = ur.recinto_id
 GROUP BY u.id
 ORDER BY u.rol, nombre;

-- 1.2 Cuántos usuarios activos hay por recinto y rol
SELECT r.codigo AS recinto, u.rol, count(*) AS usuarios
  FROM usuario u
  JOIN usuario_recinto ur ON ur.usuario_id = u.id
  JOIN recinto r          ON r.id = ur.recinto_id
 WHERE u.activo
 GROUP BY r.codigo, u.rol
 ORDER BY r.codigo, u.rol;

-- 1.3 Usuarios que nunca han ingresado o que no ingresan hace más de 7 días
SELECT nombre || ' ' || apellido AS nombre, email, rol,
       COALESCE(to_char(ultimo_acceso AT TIME ZONE 'America/Santiago', 'DD-MM-YYYY HH24:MI'), 'nunca') AS ultimo_acceso
  FROM usuario
 WHERE activo AND (ultimo_acceso IS NULL OR ultimo_acceso < now() - interval '7 days')
 ORDER BY ultimo_acceso NULLS FIRST;


-- ---------------------------------------------------------------------
-- 2. RECINTOS, GÓNDOLAS Y CÁMARAS
-- ---------------------------------------------------------------------

-- 2.1 Recintos con su umbral, góndolas, cámaras y tickets abiertos
SELECT r.codigo, r.nombre, r.comuna, r.carpeta_imagenes, r.umbral_vacio AS umbral_pct,
       (SELECT count(*) FROM gondola g WHERE g.recinto_id = r.id AND g.activo)              AS gondolas,
       (SELECT count(*) FROM v_camara_estado c WHERE c.recinto_id = r.id AND c.activa)      AS camaras,
       (SELECT count(*) FROM v_camara_estado c WHERE c.recinto_id = r.id AND c.en_linea)    AS camaras_en_linea,
       (SELECT count(*) FROM ticket t WHERE t.recinto_id = r.id
                                        AND t.estado IN ('ABIERTO','ASIGNADO','EN_PROGRESO')) AS tickets_activos
  FROM recinto r
 ORDER BY r.codigo;

-- 2.2 Góndolas con la cámara que las enfoca
SELECT r.codigo AS recinto, g.codigo AS gondola, g.pasillo, g.categoria, g.activo,
       c.codigo AS camara
  FROM gondola g
  JOIN recinto r      ON r.id = g.recinto_id
  LEFT JOIN camara c  ON c.gondola_id = g.id
 ORDER BY r.codigo, g.codigo;

-- 2.3 Estado de las cámaras (en línea = mandó foto dentro de 2× su intervalo)
SELECT recinto_codigo AS recinto, codigo AS camara, gondola_codigo AS gondola, categoria,
       CASE WHEN en_linea THEN 'En línea' WHEN activa THEN 'SIN SEÑAL' ELSE 'Desactivada' END AS estado,
       to_char(ultima_captura AT TIME ZONE 'America/Santiago', 'DD-MM HH24:MI')          AS ultima_foto,
       round(EXTRACT(EPOCH FROM now() - ultima_captura) / 60)                            AS minutos_sin_foto,
       intervalo_captura_seg / 60                                                        AS cada_min,
       ultimo_error
  FROM v_camara_estado
 ORDER BY en_linea, recinto_codigo, codigo;


-- ---------------------------------------------------------------------
-- 3. TICKETS
-- ---------------------------------------------------------------------

-- 3.1 Bandeja: tickets activos y cerrados hoy (lo mismo que ve el supervisor)
SELECT numero, recinto_codigo AS recinto, titulo, estado, prioridad, origen,
       porcentaje_vacio AS vacio_pct, producto_faltante,
       asignado_nombre AS asignado_a, minutos_abierto, num_comentarios, cierre_verificado
  FROM v_ticket_resumen
 WHERE estado IN ('ABIERTO','ASIGNADO','EN_PROGRESO')
    OR (estado = 'CERRADO' AND (cerrado_en AT TIME ZONE 'America/Santiago')::date = (now() AT TIME ZONE 'America/Santiago')::date)
 ORDER BY recinto, CASE estado WHEN 'ABIERTO' THEN 0 WHEN 'ASIGNADO' THEN 1 WHEN 'EN_PROGRESO' THEN 2 ELSE 3 END,
          prioridad DESC, creado_en DESC;

-- 3.2 Todos los tickets (historial completo)
SELECT numero, recinto_codigo AS recinto, gondola_codigo AS gondola, estado, prioridad, origen,
       pct_apertura, porcentaje_vacio AS pct_actual, pct_cierre, cierre_verificado,
       creado_por_nombre AS creado_por, asignado_nombre AS asignado_a,
       to_char(creado_en  AT TIME ZONE 'America/Santiago', 'DD-MM-YYYY HH24:MI') AS creado,
       to_char(cerrado_en AT TIME ZONE 'America/Santiago', 'DD-MM-YYYY HH24:MI') AS cerrado
  FROM v_ticket_resumen
 ORDER BY creado_en DESC;

-- 3.3 Conteo de tickets por recinto y estado
SELECT recinto_codigo AS recinto, estado, count(*) AS tickets
  FROM v_ticket_resumen
 GROUP BY recinto_codigo, estado
 ORDER BY recinto_codigo, estado;

-- 3.4 Detalle de UN ticket (cambia INC000001)
SELECT numero, titulo, estado, prioridad, origen, recinto_codigo, gondola_codigo, camara_codigo,
       porcentaje_vacio, umbral_vacio, producto_faltante, enriquecido_ia, categoria_producto, descripcion,
       creado_por_nombre, asignado_nombre, asignado_por_nombre, creado_en, asignado_en, cerrado_en
  FROM v_ticket_resumen
 WHERE numero = 'INC000001';

-- 3.5 Fotos (evidencias) de ese ticket con su resultado del modelo
SELECT ti.tipo, to_char(i.capturada_en AT TIME ZONE 'America/Santiago', 'DD-MM HH24:MI:SS') AS capturada,
       i.origen, c.codigo AS camara, u.nombre || ' ' || u.apellido AS subida_por, i.estado,
       p.porcentaje_vacio, p.umbral_aplicado, p.supera_umbral, p.num_vacios, p.tiempo_inferencia_ms,
       i.ruta_archivo, p.ruta_imagen_anotada
  FROM ticket t
  JOIN ticket_imagen ti     ON ti.ticket_id = t.id
  JOIN imagen i             ON i.id = ti.imagen_id
  LEFT JOIN camara c        ON c.id = i.camara_id
  LEFT JOIN usuario u       ON u.id = i.subida_por
  LEFT JOIN prediccion p    ON p.imagen_id = i.id
 WHERE t.numero = 'INC000001'
 ORDER BY i.capturada_en;

-- 3.6 Historial (auditoría) de ese ticket: quién cambió qué
SELECT to_char(h.creado_en AT TIME ZONE 'America/Santiago', 'DD-MM HH24:MI:SS') AS cuando,
       COALESCE(u.nombre || ' ' || u.apellido, 'Sistema') AS quien,
       h.estado_anterior, h.estado_nuevo,
       ua.nombre || ' ' || ua.apellido AS asignado_antes,
       un.nombre || ' ' || un.apellido AS asignado_despues
  FROM historial_ticket h
  JOIN ticket t        ON t.id = h.ticket_id
  LEFT JOIN usuario u  ON u.id = h.usuario_id
  LEFT JOIN usuario ua ON ua.id = h.asignado_anterior
  LEFT JOIN usuario un ON un.id = h.asignado_nuevo
 WHERE t.numero = 'INC000001'
 ORDER BY h.creado_en;

-- 3.7 Comentarios de ese ticket
SELECT to_char(c.creado_en AT TIME ZONE 'America/Santiago', 'DD-MM HH24:MI') AS cuando,
       u.nombre || ' ' || u.apellido AS autor, u.rol, c.texto
  FROM comentario c
  JOIN ticket t  ON t.id = c.ticket_id
  JOIN usuario u ON u.id = c.usuario_id
 WHERE t.numero = 'INC000001'
 ORDER BY c.creado_en;

-- 3.8 Carga de trabajo de cada reponedor (panel "Equipo de turno")
SELECT r.codigo AS recinto, v.reponedor, v.asignados, v.en_progreso, v.cerrados_hoy
  FROM v_carga_reponedor v
  JOIN recinto r ON r.id = v.recinto_id
 ORDER BY r.codigo, v.asignados + v.en_progreso DESC;


-- ---------------------------------------------------------------------
-- 4. FOTOS Y MODELO DE VISIÓN
-- ---------------------------------------------------------------------

-- 4.1 Últimas 50 fotos recibidas y su resultado
SELECT i.id, r.codigo AS recinto, i.origen,
       COALESCE(c.codigo, u.nombre || ' ' || u.apellido) AS camara_o_usuario,
       g.codigo AS gondola, i.estado,
       p.porcentaje_vacio AS vacio_pct, p.supera_umbral, p.num_vacios, p.tiempo_inferencia_ms AS ms,
       to_char(i.recibida_en AT TIME ZONE 'America/Santiago', 'DD-MM HH24:MI:SS') AS recibida,
       round(EXTRACT(EPOCH FROM i.procesada_en - i.recibida_en)::numeric, 1)    AS espera_s,
       i.tomada_por AS worker, i.ruta_archivo
  FROM imagen i
  JOIN recinto r        ON r.id = i.recinto_id
  LEFT JOIN camara c    ON c.id = i.camara_id
  LEFT JOIN usuario u   ON u.id = i.subida_por
  LEFT JOIN gondola g   ON g.id = i.gondola_id
  LEFT JOIN prediccion p ON p.imagen_id = i.id
 ORDER BY i.recibida_en DESC
 LIMIT 50;

-- 4.2 Cola de análisis: cuántas fotos hay en cada estado por recinto
SELECT r.codigo AS recinto, i.estado, count(*) AS fotos,
       to_char(min(i.recibida_en) AT TIME ZONE 'America/Santiago', 'DD-MM HH24:MI') AS mas_antigua
  FROM imagen i
  JOIN recinto r ON r.id = i.recinto_id
 GROUP BY r.codigo, i.estado
 ORDER BY r.codigo, i.estado;

-- 4.3 Fotos con error y su causa
SELECT i.id, r.codigo AS recinto, i.ruta_archivo, i.intentos, left(i.error_detalle, 200) AS error,
       to_char(i.recibida_en AT TIME ZONE 'America/Santiago', 'DD-MM HH24:MI') AS recibida
  FROM imagen i
  JOIN recinto r ON r.id = i.recinto_id
 WHERE i.estado = 'ERROR'
 ORDER BY i.recibida_en DESC;

-- 4.4 Cajas de "vacío" que detectó el modelo en una foto (cambia el id)
SELECT d.clase, d.confianza, round(d.x_min::numeric, 3) AS x_min, round(d.y_min::numeric, 3) AS y_min,
       round(d.x_max::numeric, 3) AS x_max, round(d.y_max::numeric, 3) AS y_max
  FROM deteccion d
  JOIN prediccion p ON p.id = d.prediccion_id
 WHERE p.imagen_id = (SELECT max(id) FROM imagen WHERE estado = 'PROCESADA')
 ORDER BY d.confianza DESC;

-- 4.5 Rendimiento del modelo por día: fotos, tiempo de inferencia y espera en cola
SELECT (p.creada_en AT TIME ZONE 'America/Santiago')::date AS dia,
       m.nombre || ' ' || m.version AS modelo,
       count(*) AS fotos,
       round(avg(p.tiempo_inferencia_ms)) AS ms_promedio,
       percentile_cont(0.95) WITHIN GROUP (ORDER BY p.tiempo_inferencia_ms) AS ms_p95,
       round(avg(EXTRACT(EPOCH FROM i.procesada_en - i.recibida_en))::numeric, 1) AS espera_promedio_s,
       count(*) FILTER (WHERE p.supera_umbral) AS sobre_umbral
  FROM prediccion p
  JOIN imagen i    ON i.id = p.imagen_id
  JOIN modelo_ia m ON m.id = p.modelo_id
 GROUP BY 1, 2
 ORDER BY 1 DESC;

-- 4.6 Modelos registrados (el activo primero)
SELECT id, nombre, version, familia, activo, ruta_pesos, umbral_confianza,
       parametros ->> 'pixeles_max' AS pixeles_max, parametros ->> 'hilos_recomendados' AS hilos,
       metricas ->> 'iou_vacio' AS iou_vacio, metricas ->> 'iou_gondola' AS iou_gondola,
       to_char(activado_en AT TIME ZONE 'America/Santiago', 'DD-MM-YYYY HH24:MI') AS activado
  FROM modelo_ia
 ORDER BY activo DESC, cargado_en DESC;


-- ---------------------------------------------------------------------
-- 5. NOTIFICACIONES Y PUSH
-- ---------------------------------------------------------------------

-- 5.1 Últimas notificaciones: a quién, de qué y si llegó el push
SELECT to_char(n.creada_en AT TIME ZONE 'America/Santiago', 'DD-MM HH24:MI') AS cuando,
       u.nombre || ' ' || u.apellido AS para, u.rol, n.tipo, t.numero AS ticket, n.mensaje,
       n.leida, n.enviada_push, n.push_error
  FROM notificacion n
  JOIN usuario u     ON u.id = n.usuario_id
  LEFT JOIN ticket t ON t.id = n.ticket_id
 ORDER BY n.creada_en DESC
 LIMIT 50;

-- 5.2 Notificaciones sin leer por usuario
SELECT u.nombre || ' ' || u.apellido AS usuario, u.rol, count(*) AS sin_leer
  FROM notificacion n
  JOIN usuario u ON u.id = n.usuario_id
 WHERE NOT n.leida
 GROUP BY u.id
 ORDER BY sin_leer DESC;

-- 5.3 Celulares (FCM) y navegadores (Web Push) registrados para recibir push
SELECT u.nombre || ' ' || u.apellido AS usuario, 'App ' || d.plataforma AS destino,
       left(d.token, 25) || '…' AS identificador,
       to_char(d.actualizado_en AT TIME ZONE 'America/Santiago', 'DD-MM-YYYY HH24:MI') AS actualizado
  FROM dispositivo_push d JOIN usuario u ON u.id = d.usuario_id
UNION ALL
SELECT u.nombre || ' ' || u.apellido, 'Navegador', left(w.endpoint, 40) || '…',
       to_char(w.creado_en AT TIME ZONE 'America/Santiago', 'DD-MM-YYYY HH24:MI')
  FROM web_push_suscripcion w JOIN usuario u ON u.id = w.usuario_id
 ORDER BY 1;


-- ---------------------------------------------------------------------
-- 6. IA DE PRODUCTO (GROQ)
-- ---------------------------------------------------------------------

-- 6.1 Configuración actual (la API key NO está en la BD: vive en el .env)
SELECT activo, proveedor, modelo, recortar_a_gondola,
       to_char(actualizado_en AT TIME ZONE 'America/Santiago', 'DD-MM-YYYY HH24:MI') AS actualizado
  FROM configuracion_ia;

-- 6.2 Últimos análisis de IA: qué producto sugirió y con qué confianza
SELECT to_char(a.creado_en AT TIME ZONE 'America/Santiago', 'DD-MM HH24:MI') AS cuando,
       t.numero AS ticket, a.proveedor, a.modelo, a.exitoso,
       a.productos_faltantes -> 0 ->> 'producto'  AS producto_sugerido,
       a.productos_faltantes -> 0 ->> 'confianza' AS confianza,
       a.latencia_ms, a.tokens_entrada, a.tokens_salida, a.error_detalle
  FROM analisis_ia a
  LEFT JOIN ticket t ON t.id = a.ticket_id
 ORDER BY a.creado_en DESC
 LIMIT 30;

-- 6.3 Tareas de IA en cola o con error
SELECT id, tipo, estado, intentos, payload ->> 'imagen_id' AS imagen, payload ->> 'ticket_id' AS ticket,
       to_char(disponible_en AT TIME ZONE 'America/Santiago', 'DD-MM HH24:MI:SS') AS disponible,
       left(error, 150) AS error
  FROM tarea
 ORDER BY creada_en DESC
 LIMIT 30;


-- ---------------------------------------------------------------------
-- 7. REPORTES
-- ---------------------------------------------------------------------

-- 7.1 Tickets abiertos y cerrados por día (últimos 14 días)
SELECT d::date AS dia,
       (SELECT count(*) FROM ticket t WHERE (t.creado_en  AT TIME ZONE 'America/Santiago')::date = d::date) AS abiertos,
       (SELECT count(*) FROM ticket t WHERE t.estado = 'CERRADO'
                                        AND (t.cerrado_en AT TIME ZONE 'America/Santiago')::date = d::date) AS cerrados
  FROM generate_series((now() AT TIME ZONE 'America/Santiago')::date - 13,
                       (now() AT TIME ZONE 'America/Santiago')::date, interval '1 day') d
 ORDER BY dia DESC;

-- 7.2 Tiempos promedio por recinto: cuánto tarda en asignarse y en cerrarse un ticket
SELECT recinto_codigo AS recinto,
       count(*) AS tickets,
       round(avg(EXTRACT(EPOCH FROM asignado_en - creado_en) / 60) FILTER (WHERE asignado_en IS NOT NULL)) AS min_hasta_asignar,
       round(avg(minutos_abierto) FILTER (WHERE estado = 'CERRADO')) AS min_hasta_cerrar,
       count(*) FILTER (WHERE estado = 'CERRADO') AS cerrados,
       count(*) FILTER (WHERE cierre_verificado)  AS cerrados_con_foto
  FROM v_ticket_resumen
 GROUP BY recinto_codigo
 ORDER BY recinto_codigo;

-- 7.3 Categorías con más vacíos
SELECT COALESCE(categoria, 'Sin categoría') AS categoria, count(*) AS tickets,
       round(avg(porcentaje_vacio), 1) AS vacio_promedio_pct
  FROM v_ticket_resumen
 GROUP BY 1
 ORDER BY tickets DESC;

-- 7.4 Productos que más faltan (según reponedores e IA)
SELECT producto_faltante, count(*) AS veces, bool_or(enriquecido_ia) AS sugerido_por_ia
  FROM ticket
 WHERE producto_faltante IS NOT NULL
 GROUP BY producto_faltante
 ORDER BY veces DESC
 LIMIT 20;


-- ---------------------------------------------------------------------
-- 8. MANTENIMIENTO (solo lectura)
-- ---------------------------------------------------------------------

-- 8.1 Migraciones aplicadas
SELECT version, nombre, left(sha256, 12) AS sha256,
       to_char(aplicada_en AT TIME ZONE 'America/Santiago', 'DD-MM-YYYY HH24:MI') AS aplicada
  FROM schema_migrations
 ORDER BY version;

-- 8.2 Tamaño de cada tabla
SELECT relname AS tabla, n_live_tup AS filas,
       pg_size_pretty(pg_total_relation_size(relid)) AS tamano
  FROM pg_stat_user_tables
 ORDER BY pg_total_relation_size(relid) DESC;
