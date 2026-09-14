#!/bin/bash
set -euo pipefail

DMG_PATH="${1:?Usage: smoke-test-macos-dmg.sh PATH_TO_DMG}"
DMG_PATH="$(cd "$(dirname "$DMG_PATH")" && pwd)/$(basename "$DMG_PATH")"
MOUNT_DIR="$(mktemp -d)"
STATE_DIR="$(mktemp -d)"
PIDS=()

cleanup() {
  for pid in "${PIDS[@]}"; do
    if kill -0 "$pid" 2>/dev/null; then
      kill "$pid" 2>/dev/null || true
      wait "$pid" 2>/dev/null || true
    fi
  done
  hdiutil detach "$MOUNT_DIR" -quiet 2>/dev/null || true
  rm -rf "$MOUNT_DIR" "$STATE_DIR"
}
trap cleanup EXIT

fail_with_log() {
  local name="$1"
  local log="$2"
  echo "$name failed to start from the mounted DMG"
  if [[ -f "$log" ]]; then
    cat "$log"
  fi
  exit 1
}

wait_for_url() {
  local name="$1"
  local pid="$2"
  local url="$3"
  local log="$4"
  for _ in {1..60}; do
    if ! kill -0 "$pid" 2>/dev/null; then
      fail_with_log "$name" "$log"
    fi
    if curl --fail --silent "$url" >/dev/null; then
      return 0
    fi
    sleep 1
  done
  fail_with_log "$name" "$log"
}

hdiutil attach "$DMG_PATH" -mountpoint "$MOUNT_DIR" -nobrowse -readonly -quiet
APP_DIR="$MOUNT_DIR/Bank Reporter.app"
RESOURCES="$APP_DIR/Contents/Resources"
RUNTIME="$RESOURCES/runtime"
ELECTRON_NODE="$APP_DIR/Contents/MacOS/Bank Reporter"
API_EXECUTABLE="$RUNTIME/api/bank-reporter-api/bank-reporter-api"

test -x "$ELECTRON_NODE"
test -x "$API_EXECUTABLE"
test -f "$RUNTIME/web/server.js"
test -f "$RUNTIME/web/modules/next/package.json"
test -f "$RUNTIME/browser/server.mjs"
test -d "$RUNTIME/browser/node_modules"

COMMON_PATH="/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin"

(
  cd "$RUNTIME/browser"
  env \
    PATH="$COMMON_PATH" \
    ELECTRON_RUN_AS_NODE=1 \
    AGENT_BROWSER_NODE_PATH="$ELECTRON_NODE" \
    AGENT_BROWSER_NO_WEBMCP=1 \
    AGENT_BROWSER_CONTENT_BOUNDARIES=1 \
    PLAYWRIGHT_BROWSERS_PATH="$RUNTIME/browsers" \
    HOST=127.0.0.1 \
    PORT=53192 \
    "$ELECTRON_NODE" server.mjs
) >"$STATE_DIR/browser.log" 2>&1 &
BROWSER_PID=$!
PIDS+=("$BROWSER_PID")
wait_for_url "browser" "$BROWSER_PID" "http://127.0.0.1:53192/health" "$STATE_DIR/browser.log"

env \
  PATH="$COMMON_PATH" \
  ENVIRONMENT=test \
  TASK_BACKEND=local \
  DATA_DIR="$STATE_DIR/data" \
  DATABASE_URL="sqlite:///$STATE_DIR/bank-reporter.sqlite3" \
  HOST=127.0.0.1 \
  PORT=53191 \
  BROWSER_SERVICE_URL=http://127.0.0.1:53192 \
  LIEFLAT_DIR="$RUNTIME/lieflat-charts" \
  WEB_ORIGIN=http://127.0.0.1:53190 \
  "$API_EXECUTABLE" >"$STATE_DIR/api.log" 2>&1 &
API_PID=$!
PIDS+=("$API_PID")
wait_for_url "api" "$API_PID" "http://127.0.0.1:53191/health" "$STATE_DIR/api.log"

(
  cd "$RUNTIME/web"
  env \
    PATH="$COMMON_PATH" \
    ELECTRON_RUN_AS_NODE=1 \
    NODE_ENV=production \
    NODE_PATH="$RUNTIME/web/modules" \
    HOSTNAME=127.0.0.1 \
    PORT=53190 \
    "$ELECTRON_NODE" server.js
) >"$STATE_DIR/web.log" 2>&1 &
WEB_PID=$!
PIDS+=("$WEB_PID")
wait_for_url "web" "$WEB_PID" "http://127.0.0.1:53190" "$STATE_DIR/web.log"

echo "Mounted DMG smoke test passed: web, API, and browser are healthy"
