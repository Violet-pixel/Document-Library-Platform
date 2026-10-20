#!/bin/sh
# Sobe o servidor web: aplica as migrações, cria a demonstração (num banco vazio) e inicia o Uvicorn.
set -e
python manage.py migrate --noinput
if [ "${APP_SEED_DEMO:-true}" = "true" ]; then
  python manage.py seed_demo
fi
exec uvicorn config.asgi:application --host 0.0.0.0 --port 8000 \
  --workers "${WEB_WORKERS:-2}" --proxy-headers --forwarded-allow-ips="*" --no-server-header
