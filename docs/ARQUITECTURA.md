# StockEye · Arquitectura

## Visión general

```
 Capturador (cada recinto) ─┐                          ┌─► worker ×N      inferencia ONNX (CPU ≤3 s/foto)
 App Android (reponedor) ───┼─► api (FastAPI async) ───┤    turnos por recinto · SKIP LOCKED · lease
 Panel web (nginx) ─────────┘   guarda la foto,        ├─► notificador    FCM (app) + Web Push (panel)
        ▲ SSE                   INSERT + NOTIFY        └─► ia             Groq (intercambiable)
        └──────────── PostgreSQL 16: datos, colas y eventos (LISTEN/NOTIFY) ──────────┘
                      volumen compartido /data/recintos/R0X/AAAA/MM/DD/
```

**Principio:** la api **nunca** hace trabajo pesado. Recibe la foto, la guarda en la carpeta del recinto, inserta la `imagen` como `PENDIENTE` y responde `202`. Todo lo lento lo hace un microservicio:
- la inferencia, en `worker`;
- el push, en `notificador`;
- la llamada al LLM, en `ia`.

Cada microservicio se escala de forma independiente y tiene su propia cola. Si Groq o Firebase se caen, la detección de vacíos sigue funcionando.

No se usa un broker adicional (Redis, RabbitMQ): PostgreSQL hace de cola con `FOR UPDATE SKIP LOCKED` y de bus de eventos con `LISTEN/NOTIFY`. Con decenas o cientos de cámaras sobra capacidad, y queda un solo componente que respaldar. Si algún día se necesita, la cola se puede mover a Redis Streams sin tocar la lógica de negocio, que vive en la BD.

## Servicios

| Servicio | Código | Entrada | Salida |
|---|---|---|---|
| api | `backend/stockeye/api/` | HTTP (JWT o `X-API-Key`) | filas en la BD, archivos en `/data`, SSE |
| worker | `backend/stockeye/inferencia/worker.py` | `imagen` PENDIENTE (`LISTEN imagen_nueva`) | `prediccion`, `deteccion`, `*_pred.jpg`, tickets (función de la BD), tareas de IA |
| notificador | `backend/stockeye/notificador/` | `notificacion` sin enviar (`LISTEN notificacion_nueva`) | FCM HTTP v1, Web Push (VAPID) |
| importador | `backend/stockeye/importador/` | archivos en `entradas/<RECINTO>/<GÓNDOLA>/` | `imagen` PENDIENTE (vía la fuente de carga de la góndola) |
| ia | `backend/stockeye/ia/` | `tarea` ANALISIS_IA (`LISTEN tarea_nueva`) | `analisis_ia`, `ticket.producto_faltante` |
| web | `web/` | navegador | SPA React; nginx hace de proxy de `/api` |
| capturador | `capturador/` (en el recinto) | cámaras RTSP/HTTP | `POST /api/v1/ingesta` |

## Colas y concurrencia

**Inferencia (`imagen`):**
- **Toma atómica:** `UPDATE imagen SET estado='PROCESANDO', tomada_por, tomada_en, intentos=intentos+1 WHERE id = (SELECT … FOR UPDATE SKIP LOCKED)`. N workers nunca toman la misma foto (lo prueba `tests/test_cola.py::test_varios_workers_nunca_toman_la_misma_imagen`).
- **Turnos por recinto:** el worker lista los recintos con pendientes y toma la foto más antigua del siguiente recinto, en round-robin. Una ráfaga de R01 no deja esperando a R02 (`test_rafaga_de_un_recinto_no_bloquea_a_otro`; medido: R02 esperó 7,9 s de mediana contra 34 s de R01).
- **Workers dedicados:** `WORKER_RECINTOS=R01` limita al worker a ese recinto.
- **Lease:** si un worker muere, `fn_recuperar_imagenes()` devuelve a la cola las fotos `PROCESANDO` de más de `LEASE_MINUTOS`. Al tercer intento la foto pasa a `ERROR`. Los errores permanentes (archivo faltante o imagen corrupta) van directo a `ERROR`.
- **Recarga del modelo en caliente:** `LISTEN modelo_activado`.

**Push (`notificacion`):** las filas las crean la BD (triggers) y la api. El notificador las bloquea con `SKIP LOCKED` mientras envía, así varias réplicas no duplican el push. Hace hasta 5 intentos y borra los tokens inválidos.

**IA (`tarea`):** cola genérica con `disponible_en` para reintentos con espera exponencial y para respetar el `retry-after` de Groq.

## Reglas de negocio en la BD

La fuente de verdad es `db/migraciones/001_esquema.sql`; el detalle está en PLAN.md §6 y §7. La api ejecuta `SET LOCAL app.usuario_id` en cada transacción, para que los triggers registren el autor.

- `fn_ticket_desde_prediccion`: ticket nuevo o SEGUIMIENTO; prioridad según el %.
- `trg_ticket_reglas`: solo se asigna a reponedores activos del mismo recinto; ABIERTO pasa a ASIGNADO.
- `trg_ticket_historial`: auditoría y aviso al asignado.
- 002 agrega:
  - avisos por comentario y cierre;
  - `pg_notify` para todos los eventos;
  - `fn_encolar_analisis_ia` y `fn_aplicar_analisis_ia`;
  - la vista `v_camara_estado`.

**Decisiones del flujo:**
- **Foto de cámara:** el worker abre el ticket (o agrega SEGUIMIENTO) automáticamente.
- **Foto de la app:** el worker solo analiza. El reponedor ve el resultado y decide *Crear ticket*; la api llama a la misma `fn_ticket_desde_prediccion` dentro de su transacción. Bajo el umbral también puede reportarlo.
- **Cierre:** si la última foto de CIERRE queda bajo el umbral, el cierre es verificado. Sin eso se puede cerrar igual, pero **con comentario obligatorio**.

## Inferencia

- `MotorVacio` es la interfaz; hay dos implementaciones: `MotorSegFormerOnnx`, la que se usa, y `MotorYoloOnnx`, alternativa. La familia se elige con `modelo_ia.familia`.
- **SegFormer MiT-b1 exportado a ONNX**, con onnxruntime en CPU. Sin PyTorch en el servidor:
  - la RAM del worker baja a ~0,9 GB;
  - la imagen del worker pesa 690 MB.
- **Resolución limitada por total de píxeles** (740 mil): el tiempo no depende de la proporción de la foto. Los JPEG de 12 MP se decodifican ya reducidos.
- **% vacío** = |vacío ∩ góndola| / |góndola|, sin contar el fondo. Las cajas de `deteccion` son los componentes conexos de "vacío", y la imagen anotada se guarda como `*_pred.jpg`.
- Si se define una ROI por cámara (`camara.roi`), se recorta antes de inferir. La misma ROI se usa para recortar la foto que va a la IA, por privacidad.

**Fotos cargadas (carpeta o panel).** Cada góndola tiene una "fuente de carga", una cámara de tipo `CARGA` que crea `fn_fuente_carga()` (003). Las fotos cargadas entran como fotos de cámara de esa fuente:
- reutilizan la misma regla de tickets y seguimiento;
- la fuente no aparece en las tablas de cámaras ni cuenta como "sin señal";
- en la bandeja se muestran como "Foto cargada".

## Seguridad

- **Login:**
  - JWT de acceso por 12 h y de refresco por 30 días;
  - claves con bcrypt;
  - usuarios invitados con clave temporal que deben cambiar al ingresar.
- **Alcance por rol y recinto** en cada endpoint (`deps.exigir_recinto`): un supervisor de R01 recibe 403 en R02. El reponedor solo ve y edita sus tickets.
- **Cámaras:** una API key por cámara que se muestra una vez; en la BD queda solo su `sha256`. Las credenciales RTSP viven solo en el capturador, y la api rechaza URLs con usuario y clave.
- **Fotos:** se sirven con **URL firmada** (HMAC con expiración) porque `<img>` no puede mandar el header `Authorization`.
- **Secretos** (JWT, Groq, Firebase, VAPID) solo en `.env` o `secretos/`, nunca en la BD.
- **Contenedores:** usuario no root, límites de memoria, PostgreSQL publicado solo en `127.0.0.1`.

## Presupuesto de memoria (4 GB)

| Servicio | Límite | Uso medido |
|---|---|---|
| postgres | 512 MB | ~50 MB |
| api (2 procesos) | 384 MB | ~150 MB |
| worker | 1,2 GB | ~920 MB |
| notificador | 160 MB | ~40 MB |
| ia | 200 MB | ~40 MB |
| web | 64 MB | ~8 MB |
| **Total** | **≈2,5 GB** | **≈1,2 GB** |
