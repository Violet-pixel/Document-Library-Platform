# Imagem da aplicação Python: o mesmo contêiner vira o servidor web (ASGI) ou o worker, conforme o comando.
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    DATA_ROOT=/data \
    APP_EXAMPLES_DIR=/app/exemplos

# UID/GID 10001 é o mesmo usuário da imagem do processador Java: os dois gravam no volume /data.
RUN groupadd --system --gid 10001 app \
 && useradd --system --uid 10001 --gid app --home-dir /app app \
 && mkdir -p /data /app/web \
 && chown app:app /data

WORKDIR /app/web
COPY web/requirements.txt ./
RUN pip install -r requirements.txt

COPY web/ ./
COPY exemplos/ /app/exemplos/
RUN APP_SECRET_KEY=build-only python manage.py collectstatic --noinput -v0 \
 && chmod +x start.sh

USER app
EXPOSE 8000
CMD ["./start.sh"]
