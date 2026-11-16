# stockeye-capturador: corre en el equipo del recinto (mini PC / Raspberry Pi).
#   docker build -t stockeye-capturador db/capturador/
#   docker run -d --restart unless-stopped --network host -v /etc/stockeye/camaras.json:/config/camaras.json:ro stockeye-capturador
FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg && rm -rf /var/lib/apt/lists/* \
 && pip install --no-cache-dir requests==2.32.* && useradd --create-home stockeye
COPY capturador.py /app/capturador.py
USER stockeye
CMD ["python", "/app/capturador.py", "/config/camaras.json"]
