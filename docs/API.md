# StockEye · API REST (`/api/v1`)

La documentación interactiva (OpenAPI) está en **`/api/docs`** con el servidor corriendo.

**Autenticación:**
- `Authorization: Bearer <acceso>` (JWT de `POST /auth/login`). Cuando vence, `POST /auth/refresco`.
- Las cámaras usan `X-API-Key`.
- SSE usa `?token=`.

Errores: `{"detail": "mensaje"}`. Las reglas de la BD se traducen así:
- **409**: asignación inválida, duplicado o estado incompatible;
- **422**: dato faltante o inválido;
- **403**: fuera del rol o del recinto del usuario.

## Autenticación

| Método | Ruta | Rol | Descripción |
|---|---|---|---|
| POST | `/auth/login` | todos | `{email, clave, origen: "web" \| "app"}` → `{acceso, refresco, usuario}` |
| POST | `/auth/refresco` | todos | `{refresco}` → tokens nuevos |
| GET | `/auth/yo` | todos | Usuario con sus recintos |
| POST | `/auth/clave` | todos | `{actual, nueva}` |

## Ingesta e imágenes

| Método | Ruta | Rol | Descripción |
|---|---|---|---|
| POST | `/ingesta` | cámara (`X-API-Key`) | multipart `foto`, `camara?`, `capturada_en?` → `202 {imagen_id, ruta}` |
| POST | `/ingesta/error` | cámara | `{detalle}`: el capturador reporta una falla (lo muestra *Diagnosticar*) |
| POST | `/imagenes/carga` | supervisor, admin | multipart `gondola_id`, `fotos[]` (hasta 50) → `202 {resultados: [{archivo, imagen_id \| error}]}`. Se tratan como fotos de cámara: abren ticket o seguimiento |
| POST | `/imagenes` | reponedor | multipart `foto`, `gondola_id` → `202 {imagen_id}`. No crea el ticket |
| GET | `/imagenes/{id}` | recinto | `estado`, `prediccion`, `detecciones`, `url`, `url_anotada`, `ia {estado, productos}`, `ticket` |
| GET | `/archivos/{ruta}?exp&firma` | URL firmada | Foto original o anotada |

## Tickets

| Método | Ruta | Rol | Descripción |
|---|---|---|---|
| GET | `/tickets` | supervisor y admin (recinto); reponedor (los suyos) | Filtros `recinto_id`, `vista` (todos, sin_asignar, asignados, en_progreso, cerrados_hoy, activos, historial), `estado`, `prioridad`, `asignado` (me, sin, id), `q`, `limite`, `desde` → `{total, conteos, tickets}` |
| GET | `/tickets/{numero}` | recinto | `{ticket, evidencias[], comentarios[], linea_tiempo[], ia, ia_pendiente, equipo[], permisos}` |
| POST | `/tickets` | reponedor, supervisor, admin | Desde una foto móvil: `{imagen_id, titulo?, producto_faltante?, comentario?}`. Manual: `{recinto_id \| gondola_id, titulo, prioridad?, asignado_a?}` |
| PATCH | `/tickets/{numero}` | supervisor y admin: todo; reponedor: los suyos (estado ASIGNADO ↔ EN_PROGRESO, producto, categoría) | `{asignado_a, estado, prioridad, titulo, descripcion, producto_faltante, categoria_producto, comentario}`. CERRADO sin foto verificada y CANCELADO exigen `comentario` |
| POST | `/tickets/{numero}/comentarios` | recinto | `{texto}` |
| POST | `/tickets/{numero}/cierre` | asignado o supervisor | multipart `foto` → `202 {imagen_id}`: foto de verificación |
| POST | `/tickets/{numero}/cerrar` | asignado o supervisor | `{comentario?}`: cierre verificado si la última foto de cierre quedó bajo el umbral; si no, exige comentario |

## Recintos, notificaciones y push

| Método | Ruta | Descripción |
|---|---|---|
| GET | `/recintos` | Recintos visibles, con cámaras en línea |
| GET | `/recintos/{id}/equipo` | Carga de cada reponedor (`v_carga_reponedor`) |
| GET | `/recintos/{id}/gondolas` | Góndolas (selector y QR de la app) |
| GET | `/recintos/{id}/camaras` | Estado de las cámaras |
| GET | `/recintos/{id}/alertas` | Aperturas y seguimientos recientes con el % anterior |
| GET | `/notificaciones` | `{no_leidas, notificaciones[]}` |
| PATCH | `/notificaciones/{id}` | `{leida}` |
| POST | `/notificaciones/leer-todas` | |
| POST / DELETE | `/dispositivos`, `/dispositivos/{token}` | Token FCM de la app |
| GET | `/webpush/clave` | Clave VAPID pública |
| POST | `/webpush/suscripciones`, `/webpush/baja` | Suscripción Web Push del navegador |
| GET | `/eventos?token=` | SSE con eventos `ticket`, `notificacion` e `imagen` |
| GET | `/reportes?recinto_id&dias` | Indicadores por día y por categoría |
| GET | `/salud` | Estado, modelo activo, cola y latencia p95 |

## Administración (`/admin`, rol ADMINISTRADOR)

| Ruta | Descripción |
|---|---|
| `GET/POST /recintos`, `PATCH /recintos/{id}` | Recintos y umbral de alerta |
| `GET/POST /gondolas`, `PATCH /gondolas/{id}` | Góndolas (GET también para supervisores) |
| `GET/POST /camaras`, `PATCH /camaras/{id}` | Cámaras. Al crear se devuelve la API key **una vez** |
| `POST /camaras/{id}/clave` | Regenera la API key |
| `GET /camaras/{id}/diagnostico` | Pasos sugeridos y últimas fotos (también para supervisores) |
| `GET/POST /usuarios`, `PATCH /usuarios/{id}` | Al invitar se devuelve la clave temporal una vez |
| `POST /usuarios/{id}/clave` | Restablece la clave (temporal) |
| `GET /modelos`, `POST /modelos` | Modelos: la subida es multipart `archivo` (.onnx) y `manifiesto` (.json) |
| `POST /modelos/{id}/activar`, `PATCH /modelos/{id}` | Activar ("Volver a esta") y ajustar `umbral_confianza` |
| `GET/PATCH /ia`, `POST /ia/probar` | Integración de IA (proveedor, modelo, activo) |
| `GET /cola` | Cola de inferencia por recinto, workers activos y tareas |
