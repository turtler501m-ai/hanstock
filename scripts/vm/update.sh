#!/usr/bin/env bash
set -euo pipefail

BRANCH="${1:-main}"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$ROOT_DIR"

echo "[update] repo: $ROOT_DIR"
echo "[update] branch: $BRANCH"

if [ ! -f ".env" ]; then
    echo "[update] missing .env. Create it from .env.example and set VM secrets first." >&2
    exit 1
fi

git fetch origin "$BRANCH"
git checkout "$BRANCH"
git pull --ff-only origin "$BRANCH"

if [ ! -x ".venv/bin/python" ]; then
    echo "[update] creating .venv"
    python3 -m venv .venv
fi

PYTHON="$ROOT_DIR/.venv/bin/python"

echo "[update] installing requirements"
"$PYTHON" -m pip install -r requirements.txt

echo "[update] restarting dashboard"
"$ROOT_DIR/scripts/vm/server.sh" restart
"$ROOT_DIR/scripts/vm/server.sh" status

echo "[update] done"
