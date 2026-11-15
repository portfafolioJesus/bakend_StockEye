# StockEye

Detección de vacíos en góndolas de supermercado. Cámaras y celulares envían fotos, un modelo de segmentación (SegFormer → ONNX) calcula el **% de vacío**, y si supera el umbral del recinto se abre un **ticket** (`INC000001`…). El supervisor lo asigna desde el panel web y el reponedor lo cierra en la app con una **foto de verificación**.

| Pieza | Carpeta | Tecnología |
|---|---|---|
| Base de datos | `db/` | PostgreSQL 16: esquema, triggers, colas y eventos |
| API + microservicios | `backend/` | FastAPI async · worker de inferencia (onnxruntime, CPU ≤3 s/foto) · notificador (FCM + Web Push) · IA de producto (Groq, intercambiable) |
| Panel web | `web/` | React + Vite + TypeScript + Tailwind (supervisor y administrador) |
| App Android | `StockEye-app-movil/app-movil/` | Kotlin + Compose · CameraX · Retrofit · FCM (reponedor) |
| Capturador | `capturador/` | Python + ffmpeg, corre en cada recinto |
| Backend anterior | `StockEye_backend_local/` | Legado: de aquí se portó el modelo SegFormer |

## Inicio rápido

```bash
cp .env.example .env            # completar POSTGRES_PASSWORD y JWT_SECRETO (openssl rand -hex 32)
docker compose up -d --build
docker compose exec api python -m stockeye.cli modelo registrar /modelos/segformer-mit-b1-v1.json --activar
docker compose --profile demo run --rm seed      # opcional: datos de demostración
# Fotos reales: cópialas a entradas/R01/<GÓNDOLA>/ o usa "Subir fotos" en el panel
# Panel: http://localhost:8080  ·  API: http://localhost:8080/api/docs  ·  DBeaver: localhost:5433
```

## Documentación

- [docs/MANUAL_INSTALACION.md](docs/MANUAL_INSTALACION.md): instalación, DBeaver, modelo, push, Groq, app, capturador, producción y problemas comunes.
- [docs/ARQUITECTURA.md](docs/ARQUITECTURA.md): microservicios, colas por recinto, seguridad y memoria.
- [docs/API.md](docs/API.md): endpoints.
- [PLAN.md](PLAN.md): plan funcional, reglas de negocio y hoja de ruta.
