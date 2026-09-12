#!/bin/bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
RUNTIME_DIR="$PROJECT_DIR/apps/desktop/.runtime"
ARCH="${1:-arm64}"

case "$ARCH" in
  arm64|x64) ;;
  *) echo "Architecture must be arm64 or x64" >&2; exit 2 ;;
esac

cd "$PROJECT_DIR"
rm -rf "$RUNTIME_DIR"
mkdir -p "$RUNTIME_DIR/web/.next" "$RUNTIME_DIR/api" "$RUNTIME_DIR/browser" "$RUNTIME_DIR/browsers"

zsh scripts/fetch-lieflat.sh

echo "Building Next.js desktop frontend"
npm --prefix apps/web ci --ignore-scripts
(
  cd apps/web
  API_INTERNAL_URL="http://127.0.0.1:53111" npm run build
)
cp -R apps/web/.next/standalone/. "$RUNTIME_DIR/web/"
cp -R apps/web/.next/static "$RUNTIME_DIR/web/.next/static"
cp -R apps/web/public "$RUNTIME_DIR/web/public"

echo "Building local FastAPI sidecar"
python3 -m pip install --upgrade pip
python3 -m pip install pyinstaller==6.15.0 ./services/api
python3 -m PyInstaller --noconfirm --clean --onedir \
  --name bank-reporter-api \
  --paths services/api \
  --collect-all trafilatura \
  --collect-all charset_normalizer \
  --distpath "$RUNTIME_DIR/api" \
  --workpath "$PROJECT_DIR/.runtime/pyinstaller-$ARCH" \
  --specpath "$PROJECT_DIR/.runtime" \
  services/api/desktop_entry.py

echo "Preparing agent-browser and Chromium"
npm --prefix services/browser ci
cp services/browser/server.mjs services/browser/action-policy.json services/browser/package.json "$RUNTIME_DIR/browser/"
cp -R services/browser/node_modules "$RUNTIME_DIR/browser/node_modules"
(
  cd "$RUNTIME_DIR/browser"
  PLAYWRIGHT_BROWSERS_PATH="$RUNTIME_DIR/browsers" ./node_modules/.bin/agent-browser install
)
cp -R third_party/lieflat-charts "$RUNTIME_DIR/lieflat-charts"

echo "Building unsigned macOS DMG for $ARCH"
npm --prefix apps/desktop ci
npm --prefix apps/desktop run dist -- --mac dmg "--$ARCH"
