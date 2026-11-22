# StockEye · Manual de instalación y operación

> Versión 1.0 · noviembre 2026. Cubre el servidor (PostgreSQL, API, microservicios, panel web), el modelo de visión, las notificaciones push, la IA de producto (Groq), la app Android y el capturador de cada recinto.

## Índice

1. [Qué se instala](#1-qué-se-instala)
2. [Requisitos](#2-requisitos)
3. [Instalación rápida con Docker](#3-instalación-rápida-con-docker)
4. [Base de datos y DBeaver](#4-base-de-datos-y-dbeaver)
5. [Modelo de visión (best.pt → ONNX)](#5-modelo-de-visión-bestpt--onnx)
6. [Notificaciones push (Firebase y Web Push)](#6-notificaciones-push)
7. [IA de producto con Groq](#7-ia-de-producto-con-groq)
8. [App Android](#8-app-android)
9. [Capturador en cada recinto](#9-capturador-en-cada-recinto)
10. [Desarrollo local sin Docker](#10-desarrollo-local-sin-docker)
11. [Escalado y rendimiento](#11-escalado-y-rendimiento)
12. [Puesta en producción](#12-puesta-en-producción)
13. [Problemas comunes](#13-problemas-comunes)

---

## 1. Qué se instala

```
 Cámaras IP / NVR ──► Capturador (en el recinto) ──HTTPS──┐
 App Android (reponedor) ──────────────────────────────────┤
 Navegador (supervisor / administrador) ──► web (nginx) ───┴──► api (FastAPI)
                                                                 │ guarda la foto en recintos/R0X/AAAA/MM/DD/
                                                                 │ INSERT imagen PENDIENTE + NOTIFY
                                    PostgreSQL 16 ◄──────────────┘
                     (datos + colas + eventos LISTEN/NOTIFY)
                          │                 │                    │
                 worker (inferencia)   notificador (push)   ia (Groq)
                 ONNX en CPU, ≤3 s     FCM + Web Push        producto faltante
```

| Servicio (docker compose) | Imagen | Qué hace | RAM límite |
|---|---|---|---|
| `postgres` | postgres:16-alpine | Base de datos y colas | 512 MB |
| `api` | stockeye-backend | API REST `/api/v1`, SSE en tiempo real, migraciones | 384 MB |
| `worker` | stockeye-inferencia | Analiza las fotos (SegFormer ONNX) y abre tickets | 1,2 GB |
| `notificador` | stockeye-backend | Envía push a la app (FCM) y al navegador (Web Push) | 160 MB |
| `ia` | stockeye-backend | Completa "producto faltante" con Groq (intercambiable) | 200 MB |
| `importador` | stockeye-backend | Toma las fotos que dejas en `entradas/<RECINTO>/<GÓNDOLA>/` | 160 MB |
| `web` | stockeye-web | Panel React servido por nginx; proxy de `/api` | 64 MB |

Repositorio:

```
db/              migraciones/001_esquema.sql, 002_produccion.sql · seed/seed_demo.sql · tests/test_reglas.sql
backend/         stockeye/ (api, inferencia, notificador, ia, core) · herramientas/ · modelos/ · tests/
web/             panel React + Vite + TypeScript + Tailwind
db/capturador/      capturador.py, camaras.ejemplo.json, Dockerfile, servicio systemd
StockEye-app-movil/app-movil/   app Android (Kotlin + Compose)
docker-compose.yml · docker-compose.recintos.yml · .env.example
```

## 2. Requisitos

**Servidor (producción):**

| | Mínimo | Recomendado |
|---|---|---|
| CPU | 4 núcleos x86-64 con AVX2 | 4–8 núcleos |
| RAM | 4 GB | 8 GB (permite 2–3 workers) |
| Disco | 20 GB SSD | 100 GB+: las fotos ocupan ~150–400 KB c/u |
| GPU | no necesaria | NVIDIA con 3 GB de VRAM (opcional, ver §11) |
| SO | Ubuntu 22.04/24.04 o Debian 12 | |

- **Docker Engine 24 o superior y Docker Compose v2** (`docker compose`, con espacio).
  - El `docker-compose` 1.29 (con guion) falla con Docker 25+ al recrear contenedores (`KeyError: 'ContainerConfig'`).
  - Instala v2 con `sudo apt install docker-compose-v2`, o con el plugin oficial: `sudo apt install docker-compose-plugin` desde el repositorio de Docker.
  - Verifica con `docker compose version`.
- `git` y `openssl`.

**Equipo de desarrollo (adicional):**
- Python 3.12, Node.js 22 o 24.
- Android Studio (Ladybug o superior) con JDK 21.
- DBeaver.
- Solo para convertir el modelo: ~3 GB libres para PyTorch CPU.

**Recinto:** un mini PC o Raspberry Pi 4/5 con Linux, en la misma red que las cámaras (§9).

## 3. Instalación rápida con Docker

```bash
# 1. Código
git clone <url-del-repo> stockeye && cd stockeye

# 2. Variables de entorno
cp .env.example .env
sed -i "s|^POSTGRES_PASSWORD=.*|POSTGRES_PASSWORD=$(openssl rand -hex 16)|" .env
sed -i "s|^JWT_SECRETO=.*|JWT_SECRETO=$(openssl rand -hex 32)|" .env
mkdir -p secretos backups
```

Revisa `.env`. Las variables obligatorias son `POSTGRES_PASSWORD` y `JWT_SECRETO`. Las de push y Groq se pueden completar después (§6 y §7).

```bash
# 3. Modelo de visión: deja el .onnx y su manifiesto en backend/modelos/ (ver §5)
ls backend/modelos/
#   segformer-mit-b1-v1.onnx  segformer-mit-b1-v1.json

# 4. Construir y levantar
docker compose up -d --build
docker compose ps            # todos "Up"; api, worker, web y postgres "healthy"

# 5. Registrar y activar el modelo (el worker lo carga solo, sin reiniciar)
docker compose exec api python -m stockeye.cli modelo registrar /modelos/segformer-mit-b1-v1.json --activar

# 6a. PRODUCCIÓN: crear el primer administrador (pide la clave)
docker compose exec api python -m stockeye.cli usuario crear \
    --email admin@tu-empresa.cl --nombre Ana --apellido Pérez --rol ADMINISTRADOR

# 6b. DEMO: 2 recintos, 8 usuarios, tickets de ejemplo y fotos dibujadas
docker compose --profile demo run --rm seed
#     usuarios: admin@stockeye.test · cmunoz@stockeye.test (supervisora R01) · dsoto@stockeye.test (reponedor R01)
#     clave de todos: StockEye2026!     API key de cada cámara demo: demo-<código>, ej. demo-R01-CAM03

# 7. Verificar
curl -s http://localhost:8080/api/v1/salud
```

Abre **http://localhost:8080** (o `http://IP-del-servidor:8080`) e ingresa con el administrador. La documentación interactiva de la API está en `http://localhost:8080/api/docs`.

Primeros pasos en el panel de administración:
1. **Agregar recinto**: código `R01`. Las fotos de ese recinto se guardan en `recintos/R01/AAAA/MM/DD/`.
2. **Agregar góndola**: código `P04-G01`, que es el mismo texto del QR que se pega en la góndola.
3. **Agregar cámara**: copia la API key que aparece; no se vuelve a mostrar.
4. **Invitar usuario**: se genera una clave temporal que el usuario cambia al ingresar.
5. **Integración IA**: actívala cuando tengas la key de Groq.

### 3.1 Probar con fotos reales

Hay tres formas de meter fotos reales de góndolas. Todas pasan por el mismo modelo y la misma cola.

| Forma | Cómo | Qué pasa con el ticket |
|---|---|---|
| **Carpeta** | Copia las fotos a `entradas/<RECINTO>/<GÓNDOLA>/`, ej. `entradas/R01/P04-G01/foto.jpg`. Las carpetas de cada recinto y góndola se crean solas. | Igual que una cámara: si supera el umbral se abre solo; las fotos siguientes de esa góndola quedan como seguimiento. |
| **Panel web** | Bandeja o *Góndolas y cámaras* → **Subir fotos** → elige la góndola y arrastra las fotos. | Igual que la carpeta. La ventana muestra el % de cada foto y el ticket que abrió. |
| **App Android** | *Tomar foto de góndola* o elegir desde la galería (§8). | El reponedor ve el resultado y decide *Crear ticket*. |

Detalles de la carpeta:
- El servicio `importador` la revisa cada 5 s (`IMPORTADOR_INTERVALO_S`).
- Toma solo los archivos que dejaron de cambiar hace 2 s, para no leer una foto a medio copiar.
- Las fotos cargadas pasan a `_procesadas/AAAA-MM-DD/`. Las que no son imagen válida pasan a `_rechazadas/` con un `.txt` que explica el motivo.
- Formatos: JPEG, PNG o WEBP, hasta 15 MB. Las fotos HEIC de iPhone hay que exportarlas como JPEG.
- La rotación del celular (EXIF) se corrige sola.
- La fecha de la foto es la de modificación del archivo.

Para ver el resultado:
- en el panel, el ticket nuevo aparece en la bandeja con la foto anotada (vacíos en naranjo);
- en la terminal, `docker compose logs -f importador worker`;
- en DBeaver, consulta 4.1 de `db/consultas/consultas_utiles.sql`.

Comandos útiles:

```bash
docker compose logs -f worker              # ver cada foto analizada (%, cajas, ms)
docker compose logs -f api notificador ia
docker compose restart api                 # tras cambiar .env
docker compose down                        # detener (los datos quedan en los volúmenes)
docker compose exec api python -m stockeye.cli db estado   # migraciones aplicadas
```

## 4. Base de datos y DBeaver

### 4.1 Conectarse desde DBeaver

El contenedor publica PostgreSQL en el **puerto 5433** del host, para no chocar con el PostgreSQL 16 que ya tienes en el 5432.

1. DBeaver → *Base de datos → Nueva conexión* → **PostgreSQL** → *Siguiente*.
2. Completa:

   | Campo | Valor |
   |---|---|
   | Host | `localhost` (o la IP del servidor, ver nota) |
   | Port | `5433` (`POSTGRES_PUERTO` en `.env`) |
   | Database | `stockeye` |
   | Username | `stockeye` |
   | Password | el `POSTGRES_PASSWORD` de tu `.env` |

3. *Probar conexión*. DBeaver ofrece descargar el driver la primera vez: acepta.
4. En *Bases de datos → stockeye → Esquemas → public* verás las tablas (`ticket`, `imagen`, `prediccion`, …) y las vistas (`v_ticket_resumen`, `v_carga_reponedor`, `v_camara_estado`).

> **Servidor remoto:** por seguridad el puerto solo escucha en `127.0.0.1`. Hay dos formas de conectarse desde otro equipo:
> - **Túnel SSH (recomendado):** en DBeaver, pestaña *SSH*, marca "Use SSH Tunnel" y usa el usuario y la llave del servidor. Host `localhost`, puerto `5433`.
> - **Abrir el puerto:** `POSTGRES_BIND=0.0.0.0` en `.env`, firewall solo para tu IP y `docker compose up -d postgres`.

### 4.2 Crear la BD a mano (sin Docker o en tu PostgreSQL local)

Las migraciones se aplican **en orden**. La API las aplica sola al iniciar (`AUTO_MIGRAR=true`) y registra cada una en `schema_migrations`.

Para hacerlo a mano en tu PostgreSQL local (puerto 5432):

```bash
createdb -U postgres stockeye
psql -U postgres -d stockeye -v ON_ERROR_STOP=1 -f db/migraciones/001_esquema.sql
psql -U postgres -d stockeye -v ON_ERROR_STOP=1 -f db/migraciones/002_produccion.sql
psql -U postgres -d stockeye -f db/seed/seed_demo.sql        # opcional: datos de demo
```

Desde DBeaver:
1. Clic derecho en la conexión → *Editor SQL → Abrir script SQL*.
2. Abre `db/migraciones/001_esquema.sql` y ejecútalo como script (**Alt+X**, no Ctrl+Enter, que ejecuta solo una sentencia).
3. Repite con `002_produccion.sql` y, si quieres datos de demo, con `seed/seed_demo.sql`.

> Si creas la BD a mano, la API no sabe que ya se aplicó. Para evitar que intente aplicar de nuevo, deja que la API la cree en una BD vacía (recomendado), o registra las migraciones con `python -m stockeye.cli db migrar` **antes** de ejecutar los scripts a mano.

**Reglas de migraciones:**
- Nunca edites una migración ya aplicada: la API se detiene si su hash cambió.
- Los cambios nuevos van en `db/migraciones/003_lo_que_sea.sql`, que se aplica al reiniciar la api.

**Pruebas de reglas del esquema:** `db/tests/test_reglas.sql` sobre una copia con el seed. Cada bloque debe imprimir `ok:`.

### 4.3 Consultas útiles

```sql
-- Bandeja de un recinto (lo mismo que ve el supervisor)
SELECT numero, estado, prioridad, porcentaje_vacio, asignado_nombre, minutos_abierto
  FROM v_ticket_resumen WHERE recinto_codigo = 'R01' ORDER BY creado_en DESC;

-- Cola de inferencia por recinto
SELECT r.codigo, i.estado, count(*) FROM imagen i JOIN recinto r ON r.id = i.recinto_id GROUP BY 1, 2;

-- Fotos con error y su causa
SELECT id, ruta_archivo, error_detalle FROM imagen WHERE estado = 'ERROR' ORDER BY recibida_en DESC LIMIT 20;

-- Reintentar las fotos con error
UPDATE imagen SET estado = 'PENDIENTE', intentos = 0 WHERE estado = 'ERROR';
```

### 4.4 Respaldos

```bash
# Respaldo (comprimido) en ./backups
docker compose exec -T postgres pg_dump -U stockeye -Fc stockeye > backups/stockeye_$(date +%F).dump

# Restaurar en una BD vacía
docker compose exec -T postgres pg_restore -U stockeye -d stockeye --clean --if-exists < backups/stockeye_2026-11-14.dump

# Las fotos viven en el volumen "datos":
docker run --rm -v stockeye_datos:/data -v "$PWD/backups":/b alpine tar czf /b/fotos_$(date +%F).tgz -C /data .
```

Cron diario, en `crontab -e` del servidor:

```
30 3 * * * cd /opt/stockeye && docker compose exec -T postgres pg_dump -U stockeye -Fc stockeye > backups/stockeye_$(date +\%F).dump && find backups -name '*.dump' -mtime +14 -delete
```

> El nombre real del volumen es `<proyecto>_datos`. Revísalo con `docker volume ls`; el proyecto es el nombre de la carpeta, salvo que definas `COMPOSE_PROJECT_NAME`.

## 5. Modelo de visión (best.pt → ONNX)

El modelo entregado (`best.pt`, de 55 MB) es un **SegFormer `nvidia/mit-b1`** con 3 clases: fondo, ocupado y vacío. Por el límite de **4 GB de RAM**, el servidor **no usa PyTorch**: el `.pt` se convierte a **ONNX** una vez en un PC de desarrollo y el worker lo ejecuta con onnxruntime. Así el worker usa ~0,9 GB en vez de ~2,5 GB.

```bash
cd backend
python3 -m venv .venv-herramientas
.venv-herramientas/bin/pip install -r requirements/herramientas.txt     # PyTorch CPU, ~1 GB de descarga
cp /ruta/a/best.pt modelos/best.pt
.venv-herramientas/bin/python herramientas/empaquetar_modelo.py \
    --checkpoint modelos/best.pt --version v1 --umbral 0.5 --presupuesto 3 --hilos 2 4
```

La herramienta hace cuatro pasos:
1. Reconstruye la arquitectura MiT-b1 (sin descargar nada) y valida los pesos con `strict=True`.
2. Exporta a ONNX y comprueba que la salida coincide con PyTorch (diferencia ~2e-5).
3. **Mide el tiempo en ESE equipo** con fotos 16:9, 9:16 y 4:3 de 12 MP, incluyendo decodificación, inferencia, % e imagen anotada. Elige la mayor resolución cuyo p95 quede bajo el 80 % del presupuesto (3 s).
4. Escribe el manifiesto `segformer-mit-b1-v1.json` con el umbral, la resolución, los hilos recomendados, las métricas y el benchmark.

Corre la medición en un equipo **igual al servidor**, o vuelve a ejecutarla allá con `--pixeles` para fijar la resolución.

**Medición de referencia** (Ryzen 5 3400G, 4 núcleos, sin GPU):

| Hilos | Píxeles de entrada | p50 por foto | p95 | RAM del worker |
|---|---|---|---|---|
| 2 | 740 mil (≈1152×640) | 1,8 s | 1,9 s | ~0,9 GB |
| 2 | 600 mil (≈1024×576) | 1,45 s | 1,5 s | ~0,8 GB |
| 4 | 600 mil | 1,0 s | 1,1 s | ~1,0 GB |
| 4 | 900 mil (≈1280×704) | 1,65 s | 2,0 s | ~1,5 GB |

- Las fotos de 12 MP del celular se decodifican ya reducidas (escalado DCT del JPEG).
- La resolución se limita por **total de píxeles**, así que una foto vertical u horizontal tarda lo mismo.
- Si una foto supera `INFERENCIA_PRESUPUESTO_S`, el worker lo deja en su log como `EXCEDE el presupuesto`.

**Umbral y calidad.** `--umbral` es la probabilidad mínima para marcar un píxel como "vacío". El valor validado está en el Colab (celda 6.3); si no lo tienes, 0,5 es provisional. Las métricas del checkpoint dicen `iou_vacio = 0,354` y `iou_gondola = 0,818`. Antes de producción, compara el % del modelo con la estimación de una persona en ~50 fotos reales y ajusta el umbral desde el panel: *Modelo de visión → Confianza mínima*, que se aplica en caliente.

**Cambiar de modelo:**
- Desde el panel, *Subir nuevo modelo (.onnx)* con su `.json` y luego *Volver a esta* para activar otra versión. Los workers recargan solos (LISTEN `modelo_activado`).
- Por línea de comandos: `modelo registrar ... --activar`.

**YOLO como alternativa.** El worker también soporta YOLO (Ultralytics v8/11, familia `YOLO`):
1. Exporta con `yolo export model=best.pt format=onnx imgsz=640`.
2. Crea un manifiesto con `"familia": "YOLO"`, `"clases": {"0": "vacio", "1": "producto"}`, `"umbral_confianza": 0.25` y `"parametros": {"imgsz": 640}`.
3. Regístralo igual que el de SegFormer.

## 6. Notificaciones push

### 6.1 App Android (Firebase Cloud Messaging)

1. Entra a <https://console.firebase.google.com>, crea el proyecto "StockEye" y agrega una **app Android** con el paquete `cl.duoc.stockeye`.
2. Descarga `google-services.json` y cópialo en `StockEye-app-movil/app-movil/app/`. Sin ese archivo la app compila igual, pero sin push.
3. Para el servidor: *Configuración del proyecto → Cuentas de servicio → Generar nueva clave privada*. Guarda el JSON como `secretos/firebase-cuenta-servicio.json` (`chmod 600`).
4. En `.env` queda `FCM_CREDENCIALES=/secretos/firebase-cuenta-servicio.json`. Luego `docker compose up -d notificador`.

Cuando el reponedor inicia sesión, la app registra su token en `POST /dispositivos`.
- El **notificador** envía la notificación cuando le asignan un ticket o comentan en él.
- Los supervisores reciben las alertas de vacío y los cierres.
- Los tokens inválidos se borran solos.

### 6.2 Panel web (Web Push)

```bash
docker compose run --rm api python -m stockeye.cli vapid
# copia VAPID_PUBLICA y VAPID_PRIVADA en .env, luego:
docker compose up -d api notificador
```

En el panel, la campana muestra el botón *Recibir avisos aunque el panel esté cerrado*.

> Los navegadores solo permiten Web Push en **HTTPS** (o en `localhost`). En producción, pon el panel detrás de HTTPS (§12).

Con el panel abierto, los cambios llegan en tiempo real por **SSE** (`/api/v1/eventos`), sin necesidad de push.

## 7. IA de producto con Groq

1. Crea una API key en <https://console.groq.com/keys>.
2. En `.env`, define `GROQ_API_KEY=gsk_...`. La key **nunca** se guarda en la base de datos.
3. Ejecuta `docker compose up -d api ia`.
4. En el panel, *Integración IA*: proveedor **Groq**, modelo con visión (por defecto `qwen/qwen3.8-27b`, según la [documentación de Groq](https://console.groq.com/docs/vision)), luego *Probar conexión* y activar.

Cómo funciona:
- **Foto de cámara:** al abrirse un ticket, se encola un análisis. El microservicio `ia` manda la imagen anotada (con los vacíos marcados en naranjo), recortada a la zona de la cámara si definiste ROI, y guarda la respuesta en `analisis_ia`. Si nadie escribió el producto, lo completa en el ticket.
- **Foto de la app:** si supera el umbral, la sugerencia aparece en *Resultado del análisis* con el botón "Usar".
- **Si Groq no responde:** reintenta con espera creciente y respeta el `retry-after` del límite de uso. La detección de vacíos **no depende** de la IA.

**Cambiar de proveedor.**
- Ya está registrado `openai`: define `OPENAI_API_KEY` y elígelo en el panel.
- Para otro proveedor, crea una clase con `analizar(imagen_jpg, contexto)` y `probar()` en `backend/stockeye/ia/` y regístrala con `@registrar("nombre")`.

## 8. App Android

1. Abre `StockEye-app-movil/app-movil` en Android Studio, con el JDK 21 de Android Studio en *Settings → Build Tools → Gradle → Gradle JDK*.
2. **URL del backend:**

   | Dónde corre | URL |
   |---|---|
   | Emulador | `http://10.0.2.2:8080/` (por defecto en debug) |
   | Celular en la red local | se cambia en el login → *Configurar servidor* → `http://IP-del-servidor:8080/` |
   | Release | `./gradlew assembleRelease -Pstockeye.apiUrl=https://stockeye.tu-empresa.cl/` (solo HTTPS) |

3. Compilar: `./gradlew assembleDebug`. El APK queda en `app/build/outputs/apk/debug/app-debug.apk`; instálalo con `adb install`.
4. **Release firmado:** *Build → Generate Signed App Bundle/APK* con tu keystore. Guarda el keystore fuera del repositorio.

Ingresa con un **reponedor**, por ejemplo `dsoto@stockeye.test` en la demo. Supervisores y administradores usan el panel web.

Flujo en la app:
1. **Mis tickets** (Activos / Cerrados hoy).
2. **Tomar foto de góndola**: elige la góndola o escanea su QR → **Resultado del análisis**, con el % y la sugerencia de IA → **Crear ticket**.
3. **Empezar** → **Cerrar**: foto de verificación (si queda bajo el umbral, "cierre verificado") → **Cerrar ticket**.

> El proyecto usa AGP 8.7.3 con el wrapper de Gradle 9.7.1 que ya traía. Si Android Studio reclama incompatibilidad, sube AGP desde *Tools → AGP Upgrade Assistant*, o baja el wrapper a Gradle 8.11 en `gradle/wrapper/gradle-wrapper.properties`.

**QR de las góndolas:** imprime un QR con el código exacto de la góndola (ej. `P04-G01`). La app usa el escáner de Google Play services, sin permiso extra.

## 9. Capturador en cada recinto

Corre en un mini PC o Raspberry Pi **dentro** de la red del supermercado. Lee las cámaras localmente y sube las fotos por HTTPS. **No se abren puertos ni se exponen cámaras a internet.**

1. Pide al área de TI: la IP del NVR o de cada cámara, qué canal enfoca cada góndola y un **usuario de solo lectura**.
2. Fija la IP de la cámara con una reserva DHCP por MAC en el router.
3. Prueba la URL RTSP, por ejemplo en Hikvision `rtsp://IP:554/Streaming/Channels/102`:
   ```bash
   ffmpeg -rtsp_transport tcp -i "rtsp://usuario:clave@192.168.1.20:554/Streaming/Channels/102" -frames:v 1 prueba.jpg
   ```
4. En el panel, *Agregar cámara*: la URL **sin** usuario ni clave. Copia la API key.
5. Configura e instala:
   ```bash
   sudo mkdir -p /etc/stockeye && sudo cp db/capturador/camaras.ejemplo.json /etc/stockeye/camaras.json
   sudo nano /etc/stockeye/camaras.json        # api_url, api_key, fuente, usuario/clave de solo lectura
   sudo chmod 600 /etc/stockeye/camaras.json

   # con Docker
   docker build -t stockeye-capturador db/capturador/
   docker run -d --name capturador --restart unless-stopped --network host \
       -v /etc/stockeye/camaras.json:/config/camaras.json:ro stockeye-capturador

   # o sin Docker (systemd): ver db/capturador/stockeye-capturador.service
   ```
6. En el panel, la cámara pasa a **En línea**. Si no envía fotos en 2 veces su intervalo, aparece **Sin señal** y *Diagnosticar* muestra el último error que reportó el capturador.

**Para probar sin cámaras:**
- Usa como `fuente` un video o una foto local.
- O usa un celular con la app "IP Webcam" y su URL `http://IP:8080/shot.jpg`.

## 10. Desarrollo local sin Docker

```bash
# Base de datos: el Postgres de Docker (solo ese servicio) o tu Postgres local
docker compose up -d postgres

# Backend
cd backend
python3 -m venv .venv && .venv/bin/pip install -r requirements/dev.txt
cat > .env <<'EOF'
DATABASE_URL=postgresql://stockeye:<POSTGRES_PASSWORD>@localhost:5433/stockeye
DATOS_DIR=datos
MODELOS_DIR=modelos
EOF
.venv/bin/python -m stockeye.cli db seed           # migraciones + demo
.venv/bin/python -m stockeye.cli demo imagenes     # fotos dibujadas para el demo
.venv/bin/python -m stockeye.cli api --port 8000   # http://localhost:8000/api/docs
.venv/bin/python -m stockeye.cli worker            # en otra terminal
.venv/bin/python -m stockeye.cli notificador       # opcional
.venv/bin/python -m stockeye.cli ia                # opcional

# Panel (proxy de /api → localhost:8000)
.venv/bin/python -m stockeye.cli importador        # opcional: carpeta ../entradas
cd ../web && npm ci && npm run dev                # http://localhost:5173
```

**Pruebas:**

```bash
# backend: 22 pruebas; usa la BD stockeye_test (se recrea en cada prueba)
cd backend
STOCKEYE_TEST_DATABASE_URL=postgresql://stockeye:<clave>@localhost:5433/stockeye_test .venv/bin/python -m pytest

cd ../web && npm run typecheck && npm run build                      # panel
cd backend && .venv/bin/python herramientas/simular_camaras.py \
    --api http://localhost:8080 --rafaga 30 --otras 3                # carga: ¿una ráfaga frena a otro recinto?
```

## 11. Escalado y rendimiento

Cada parte es un microservicio que se escala por separado. Todos se coordinan por PostgreSQL:
- **colas** con `FOR UPDATE SKIP LOCKED`, que impide que dos réplicas tomen la misma foto;
- **eventos** con `LISTEN/NOTIFY`, que despiertan a los servicios al instante.

**Equidad entre recintos.** El worker atiende los recintos **por turnos**: toma la foto más antigua de R01, luego la de R02, y así. Medido con 1 worker:

| Escenario | Espera de R01 | Espera de R02 |
|---|---|---|
| Ráfaga de 30 fotos de R01 encolada **antes** que 3 de R02 | mediana 34 s | mediana **7,9 s** (máx. 11,5 s) |

Sin turnos, las de R02 habrían esperado ~60 s, al final de la fila.

**Cuándo escalar:** mira *Configuración → Cola de análisis*, o `GET /api/v1/admin/cola`. Si "en cola" crece de forma sostenida o el p95 de espera supera el intervalo de las cámaras, agrega capacidad:

```bash
# Pool compartido: más workers (cada uno ~0,9 GB). Con 4 GB de RAM: máximo 2.
ORT_HILOS=2 docker compose up -d --scale worker=2

# Worker dedicado a un recinto grande (y el resto para los demás)
docker compose -f docker-compose.yml -f docker-compose.recintos.yml up -d
```

- **Regla de núcleos:** `hilos × workers ≤ núcleos físicos`.
- **Capacidad de referencia:** 1 worker de 2 hilos procesa ~32 fotos por minuto. Con fotos cada 5 minutos alcanza para ~150 cámaras.

**GPU (3 GB de VRAM).** SegFormer-b1 usa menos de 1 GB de VRAM.
1. Construye la imagen del worker con `--build-arg ORT=onnxruntime-gpu --build-arg BASE=nvidia/cuda:12.4.1-cudnn-runtime-ubuntu22.04`. Esa base necesita además `apt install python3.12`.
2. Define `INFERENCIA_DISPOSITIVO=cuda` y agrega `gpus: all` al servicio `worker`.
3. El worker limita la memoria de la GPU a `VRAM_MAX_GB` (2,5 por defecto).

## 12. Puesta en producción

**HTTPS con Caddy**, que obtiene y renueva el certificado solo. Archivo `/etc/caddy/Caddyfile`:

```
stockeye.tu-empresa.cl {
    reverse_proxy 127.0.0.1:8080
}
```

En `.env`:
- `WEB_PUERTO=127.0.0.1:8080`, para que solo Caddy lo vea;
- `ENTORNO=produccion`;
- `CORS_ORIGENES=https://stockeye.tu-empresa.cl`.

**Lista de verificación:**
- [ ] `POSTGRES_PASSWORD` y `JWT_SECRETO` aleatorios. Con `ENTORNO=produccion` la API no arranca si el secreto es débil.
- [ ] `.env` y `secretos/` con permisos 600 y **fuera de git** (ya están en `.gitignore`).
- [ ] Firewall: abrir solo 80/443 (y 22). PostgreSQL queda en `127.0.0.1`.
- [ ] HTTPS activo: la app release y Web Push lo exigen.
- [ ] Respaldos diarios de la BD y del volumen de fotos (§4.4), probando una restauración.
- [ ] Monitoreo: `GET /api/v1/salud` cada minuto (Uptime Kuma, por ejemplo). Muestra la cola y la latencia p95.
- [ ] Usuarios demo **no** cargados: no ejecutes `--profile demo` en producción.
- [ ] Umbral del modelo validado con fotos reales (§5).

**Actualizar:**

```bash
git pull
docker compose build
docker compose up -d        # la api aplica migraciones nuevas al iniciar
```

**Volver a un modelo anterior:** en el panel, *Modelo de visión → Volver a esta*.

## 13. Problemas comunes

| Síntoma | Causa y solución |
|---|---|
| `KeyError: 'ContainerConfig'` al hacer `docker-compose up` | `docker-compose` 1.29 con Docker 25+. Instala Compose v2 (`docker compose`). Mientras tanto: `docker-compose rm -sf <servicio> && docker-compose up -d <servicio>`. |
| `port is already allocated` en 5433 u 8080 | Cambia `POSTGRES_PUERTO` o `WEB_PUERTO` en `.env`. |
| El worker dice "No hay modelo activo" | Registra el modelo: `docker compose exec api python -m stockeye.cli modelo registrar /modelos/<x>.json --activar`. |
| Una foto dejada en `entradas/` no se importa | Debe estar dentro de `<RECINTO>/<GÓNDOLA>/` con códigos que existan en el panel. Revisa `docker compose logs importador` y la carpeta `_rechazadas/`. Si la carpeta `entradas` la creó Docker (dueño root), ejecuta `sudo chown -R $USER entradas`. |
| Las fotos quedan en `PENDIENTE` | `docker compose logs worker`. Revisa que `backend/modelos/` tenga el `.onnx` que indica `modelo_ia.ruta_pesos`. |
| Log "EXCEDE el presupuesto de tiempo" | El servidor es más lento que el de la medición. Vuelve a ejecutar `empaquetar_modelo.py` allá, o fija `--pixeles 600000`. |
| La cámara aparece "Sin señal" | Usa *Diagnosticar*. Mira `journalctl -u stockeye-capturador` o `docker logs capturador` en el recinto. Prueba la URL con ffmpeg. |
| `401 API key inválida` en el capturador | La clave se regeneró o se copió mal: *Configuración → cámara*, regenerar y actualizar `camaras.json`. |
| La app no conecta | En un celular real usa la IP del servidor, no `localhost`. La release exige HTTPS. Revisa el firewall del 8080. |
| No llegan push a la app | Falta `google-services.json` (Perfil lo indica) o `FCM_CREDENCIALES`. Mira `docker compose logs notificador`. En Android 13+, acepta el permiso de notificaciones. |
| No aparece "Recibir avisos" en el panel | Faltan las claves VAPID, o el panel no está en HTTPS. |
| *Probar conexión* de IA dice "API key inválida" | Revisa `GROQ_API_KEY` en `.env` y ejecuta `docker compose up -d api ia`. |
| La API no arranca: "La migración … cambió" | Se editó una migración aplicada. Revierte el archivo y crea una `003_*.sql`. |
