#!/bin/bash
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$SCRIPT_DIR"
RUNTIME_DIR="$ROOT_DIR/.runtime"
STDOUT_LOG="$RUNTIME_DIR/dashboard-server.log"
STDERR_LOG="$RUNTIME_DIR/dashboard-server.err.log"

LINES="${1:-80}"

echo "[logs] stderr tail: $STDERR_LOG"
[ -f "$STDERR_LOG" ] && tail -n "$LINES" "$STDERR_LOG"

echo ""
echo "[logs] stdout tail: $STDOUT_LOG"
[ -f "$STDOUT_LOG" ] && tail -n "$LINES" "$STDOUT_LOG"