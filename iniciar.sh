#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

if ! command -v docker >/dev/null 2>&1; then
  echo "Instale o Docker (com Docker Compose) e rode de novo: https://docs.docker.com/get-docker/"
  exit 1
fi

aleatorio() { head -c 96 /dev/urandom | base64 | tr -dc 'A-Za-z0-9' | head -c "$1"; }

if [ ! -f .env ]; then
  cp .env.example .env
  sed -i.bak \
    -e "s|^DB_PASSWORD=.*|DB_PASSWORD=$(aleatorio 40)|" \
    -e "s|^APP_SECRET_KEY=.*|APP_SECRET_KEY=$(aleatorio 64)|" .env
  rm -f .env.bak
  echo "Arquivo .env criado com senha do banco e chave secreta aleatórias."
fi

docker compose up -d --build

porta=$(grep -E '^APP_PORT=' .env | cut -d= -f2)
porta=${porta:-8080}
printf "Aguardando o Lume subir"
for _ in $(seq 1 120); do
  if curl -fsS "http://localhost:${porta}/api/health" >/dev/null 2>&1; then
    echo
    echo "Pronto!"
    echo "  Biblioteca:       http://localhost:${porta}"
    echo "  Documentação API: http://localhost:${porta}/api/docs"
    echo "  Contas: admin@lume.dev ou leitor@lume.dev, senha Lume@2026"
    exit 0
  fi
  printf "."
  sleep 2
done
echo
echo "O Lume ainda está subindo. Acompanhe com: docker compose logs -f"
