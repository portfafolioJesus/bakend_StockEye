# stockeye-backend: api, notificador y enriquecedor de IA (sin modelo de visión).
# Se construye desde la raíz del repo:  docker build -f backend/Dockerfile -t stockeye-backend .
FROM python:3.12-slim AS deps
ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
COPY backend/requirements/base.txt backend/requirements/api.txt /tmp/req/
RUN python -m venv /opt/venv && /opt/venv/bin/pip install -r /tmp/req/api.txt

FROM python:3.12-slim
ENV PATH=/opt/venv/bin:$PATH PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 \
    DATOS_DIR=/data MODELOS_DIR=/modelos DB_DIR=/app/db TZ=America/Santiago
RUN useradd --create-home --uid 1000 stockeye && mkdir -p /data /modelos && chown stockeye /data /modelos
COPY --from=deps /opt/venv /opt/venv
WORKDIR /app
COPY db /app/db
COPY backend/stockeye /app/stockeye
USER stockeye
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/v1/salud', timeout=4).status == 200 else 1)"
CMD ["python", "-m", "stockeye.cli", "api", "--host", "0.0.0.0", "--port", "8000"]
