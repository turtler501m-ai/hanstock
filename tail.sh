#!/bin/bash
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$SCRIPT_DIR"
RUNTIME_DIR="$ROOT_DIR/.runtime"
STDOUT_LOG="$RUNTIME_DIR/dashboard-server.log"
STDERR_LOG="$RUNTIME_DIR/dashboard-server.err.log"

echo "[tail] following logs. Press Ctrl+C to stop watching."
echo "[tail] stderr: $STDERR_LOG"
echo "[tail] stdout: $STDOUT_LOG"

if [ -f "$STDERR_LOG" ] && [ -f "$STDOUT_LOG" ]; then
    tail -f "$STDERR_LOG" "$STDOUT_LOG"
elif [ -f "$STDERR_LOG" ]; then
    tail -f "$STDERR_LOG"
elif [ -f "$STDOUT_LOG" ]; then
    tail -f "$STDOUT_LOG"
else
    echo "[tail] no log files found"
fi