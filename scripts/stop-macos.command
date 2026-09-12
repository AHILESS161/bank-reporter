#!/bin/zsh
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_DIR"
docker compose down
echo "Bank Reporter остановлен. Документы и база данных сохранены."
read -r "REPLY?Нажмите Enter, чтобы закрыть окно…"
