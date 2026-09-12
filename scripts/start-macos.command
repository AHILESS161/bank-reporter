#!/bin/zsh
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_DIR"

echo "Bank Reporter — подготовка запуска на macOS"

if ! command -v git >/dev/null 2>&1; then
  echo "Нужны системные инструменты Apple. Подтвердите их установку и затем запустите этот файл снова."
  xcode-select --install || true
  read -r "REPLY?Нажмите Enter, чтобы закрыть окно…"
  exit 1
fi

if ! command -v docker >/dev/null 2>&1; then
  if command -v brew >/dev/null 2>&1; then
    echo "Docker Desktop не найден. Устанавливаю через Homebrew…"
    brew install --cask docker
  else
    echo "Docker Desktop не найден. Открываю официальную страницу установки."
    open "https://www.docker.com/products/docker-desktop/"
    echo "Установите Docker Desktop, запустите его и затем повторно откройте scripts/start-macos.command."
    read -r "REPLY?Нажмите Enter, чтобы закрыть окно…"
    exit 1
  fi
fi

if ! docker info >/dev/null 2>&1; then
  echo "Запускаю Docker Desktop…"
  open -a Docker
  for attempt in {1..60}; do
    if docker info >/dev/null 2>&1; then
      break
    fi
    sleep 3
  done
fi

if ! docker info >/dev/null 2>&1; then
  echo "Docker Desktop не успел запуститься. Дождитесь статуса Running и повторите запуск." >&2
  read -r "REPLY?Нажмите Enter, чтобы закрыть окно…"
  exit 1
fi

if [ ! -f .env ]; then
  cp .env.example .env
fi

configured_key="$(sed -n 's/^MODEL_API_KEY=//p' .env | tail -n 1)"
legacy_key="$(sed -n 's/^OPENROUTER_API_KEY=//p' .env | tail -n 1)"
if [ -z "$configured_key" ] && [ -z "$legacy_key" ]; then
  echo "Введите API-ключ RouterAI. Ввод не отображается:"
  read -rs api_key
  echo
  if [ -z "$api_key" ]; then
    echo "Ключ не введен." >&2
    exit 1
  fi
  sed -i '' "s#^MODEL_API_KEY=.*#MODEL_API_KEY=$api_key#" .env
fi

zsh scripts/fetch-lieflat.sh
echo "Собираю и запускаю Bank Reporter. Первый запуск может занять несколько минут…"
docker compose up --build -d

echo "Bank Reporter запущен: http://localhost:3000"
open "http://localhost:3000"
read -r "REPLY?Нажмите Enter, чтобы закрыть окно…"
