#!/bin/bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
RUNTIME_DIR="$PROJECT_DIR/apps/desktop/.runtime"
ARCH="arm64"

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

# electron-builder deliberately filters nested directories named node_modules
# from extraResources. Preserve Next's traced standalone dependencies under a
# neutral name and expose them to Node through NODE_PATH at runtime.
test -f "$RUNTIME_DIR/web/node_modules/next/package.json"
rm -rf "$RUNTIME_DIR/web/modules"
mv "$RUNTIME_DIR/web/node_modules" "$RUNTIME_DIR/web/modules"
test -f "$RUNTIME_DIR/web/modules/next/package.json"

echo "Smoke-testing packaged Next.js frontend"
WEB_SMOKE_DIR="$(mktemp -d)"
WEB_SMOKE_PORT=53190
WEB_SMOKE_LOG="$WEB_SMOKE_DIR/web.log"
WEB_SMOKE_PID=""
cleanup_web_smoke() {
  if [[ -n "$WEB_SMOKE_PID" ]] && kill -0 "$WEB_SMOKE_PID" 2>/dev/null; then
    kill "$WEB_SMOKE_PID" 2>/dev/null || true
    wait "$WEB_SMOKE_PID" 2>/dev/null || true
  fi
  rm -rf "$WEB_SMOKE_DIR"
}
trap cleanup_web_smoke EXIT
(
  cd "$RUNTIME_DIR/web"
  NODE_PATH="$RUNTIME_DIR/web/modules" \
    HOSTNAME=127.0.0.1 \
    PORT="$WEB_SMOKE_PORT" \
    NODE_ENV=production \
    node server.js
) >"$WEB_SMOKE_LOG" 2>&1 &
WEB_SMOKE_PID=$!
WEB_SMOKE_READY=0
for _ in {1..60}; do
  if ! kill -0 "$WEB_SMOKE_PID" 2>/dev/null; then
    echo "Packaged web server exited during smoke test"
    cat "$WEB_SMOKE_LOG"
    exit 1
  fi
  if curl --fail --silent "http://127.0.0.1:$WEB_SMOKE_PORT" >/dev/null; then
    WEB_SMOKE_READY=1
    break
  fi
  sleep 1
done
if [[ "$WEB_SMOKE_READY" != "1" ]]; then
  echo "Packaged web server did not become healthy"
  cat "$WEB_SMOKE_LOG"
  exit 1
fi
kill "$WEB_SMOKE_PID" 2>/dev/null || true
wait "$WEB_SMOKE_PID" 2>/dev/null || true
WEB_SMOKE_PID=""
trap - EXIT
rm -rf "$WEB_SMOKE_DIR"

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

echo "Smoke-testing packaged FastAPI sidecar"
SMOKE_DIR="$(mktemp -d)"
SMOKE_PORT=53191
SMOKE_LOG="$SMOKE_DIR/api.log"
SMOKE_PID=""
cleanup_smoke() {
  if [[ -n "$SMOKE_PID" ]] && kill -0 "$SMOKE_PID" 2>/dev/null; then
    kill "$SMOKE_PID" 2>/dev/null || true
    wait "$SMOKE_PID" 2>/dev/null || true
  fi
  rm -rf "$SMOKE_DIR"
}
trap cleanup_smoke EXIT
ENVIRONMENT=test \
TASK_BACKEND=local \
DATA_DIR="$SMOKE_DIR/data" \
DATABASE_URL="sqlite:///$SMOKE_DIR/bank-reporter.sqlite3" \
HOST=127.0.0.1 \
PORT="$SMOKE_PORT" \
"$RUNTIME_DIR/api/bank-reporter-api/bank-reporter-api" >"$SMOKE_LOG" 2>&1 &
SMOKE_PID=$!
SMOKE_READY=0
for _ in {1..60}; do
  if ! kill -0 "$SMOKE_PID" 2>/dev/null; then
    echo "Packaged API exited during smoke test"
    cat "$SMOKE_LOG"
    exit 1
  fi
  if curl --fail --silent "http://127.0.0.1:$SMOKE_PORT/health" >/dev/null; then
    SMOKE_READY=1
    break
  fi
  sleep 1
done
if [[ "$SMOKE_READY" != "1" ]]; then
  echo "Packaged API did not become healthy"
  cat "$SMOKE_LOG"
  exit 1
fi
kill "$SMOKE_PID" 2>/dev/null || true
wait "$SMOKE_PID" 2>/dev/null || true
SMOKE_PID=""
trap - EXIT
rm -rf "$SMOKE_DIR"

echo "Preparing agent-browser and Chromium"
npm --prefix services/browser ci
cp services/browser/server.mjs services/browser/action-policy.json services/browser/package.json "$RUNTIME_DIR/browser/"
cp -R services/browser/node_modules "$RUNTIME_DIR/browser/node_modules"
(
  cd "$RUNTIME_DIR/browser"
  PLAYWRIGHT_BROWSERS_PATH="$RUNTIME_DIR/browsers" ./node_modules/.bin/agent-browser install
)
cp -R third_party/lieflat-charts "$RUNTIME_DIR/lieflat-charts"

echo "Building unsigned macOS DMG for Apple Silicon ($ARCH)"
npm --prefix apps/desktop ci
npm --prefix apps/desktop run dist -- --mac dmg "--$ARCH"

echo "Smoke-testing the mounted DMG"
DMG_PATH="$(find apps/desktop/dist -maxdepth 1 -type f -name "Bank-Reporter-*-$ARCH.dmg" -print -quit)"
test -n "$DMG_PATH"
bash scripts/smoke-test-macos-dmg.sh "$DMG_PATH"
