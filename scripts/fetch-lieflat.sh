#!/bin/zsh
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TARGET_DIR="$PROJECT_DIR/third_party/lieflat-charts"
EXPECTED_COMMIT="eace082a317b696c5570c25826a53a7fa113e984"

if [ -f "$TARGET_DIR/SKILL.md" ]; then
  current_commit="$(git -C "$TARGET_DIR" rev-parse HEAD 2>/dev/null || true)"
  if [ "$current_commit" = "$EXPECTED_COMMIT" ]; then
    exit 0
  fi
fi

if [ -d "$PROJECT_DIR/.git" ]; then
  git -C "$PROJECT_DIR" submodule update --init --recursive
else
  if [ -d "$TARGET_DIR" ] && ! find "$TARGET_DIR" -mindepth 1 -print -quit | grep -q .; then
    rmdir "$TARGET_DIR"
  fi
  if [ -e "$TARGET_DIR" ]; then
    echo "Каталог $TARGET_DIR уже существует и не пуст, но содержит не ту версию." >&2
    exit 1
  fi
  git clone https://github.com/larashero3-dotcom/lieflat-charts.git "$TARGET_DIR"
  git -C "$TARGET_DIR" checkout "$EXPECTED_COMMIT"
fi

actual_commit="$(git -C "$TARGET_DIR" rev-parse HEAD)"
if [ "$actual_commit" != "$EXPECTED_COMMIT" ]; then
  echo "Ошибка проверки lieflat-charts: ожидался $EXPECTED_COMMIT, получен $actual_commit" >&2
  exit 1
fi
