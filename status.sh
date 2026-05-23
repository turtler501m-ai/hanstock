#!/bin/bash
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$SCRIPT_DIR"
RUNTIME_DIR="$ROOT_DIR/.runtime"
PID_FILE="$RUNTIME_DIR/dashboard-server.pid"

get_listening_pids() {
    if command -v lsof >/dev/null 2>&1; then
        lsof -ti ":8000" 2>/dev/null || true
    elif command -v ss >/dev/null 2>&1; then
        ss -tlnp 2>/dev/null | grep -E "(:8000)" | grep -oP 'pid=\K[0-9]+' || true
    else
        netstat -tlnp 2>/dev/null | grep -E "[:\s]8000\s" | grep -oP '\d+/' | cut -d'/' -f1 || true
    fi
}

get_dashboard_pids() {
    pgrep -f "uvicorn.*src.dashboard" 2>/dev/null || true
}

get_pid_file_pids() {
    if [ -f "$PID_FILE" ]; then
        cat "$PID_FILE" 2>/dev/null || true
    fi
}

get_server_pids() {
    echo "$(get_pid_file_pids) $(get_listening_pids) $(get_dashboard_pids)" | tr ' ' '\n' | grep -E "^[0-9]+$" | sort -nu || true
}

listening_pids=$(get_listening_pids)
server_pids=$(get_server_pids)

if [ -n "$listening_pids" ]; then
    echo "[status] running: http://127.0.0.1:8000"
    echo "[status] listening PID: $listening_pids"
else
    echo "[status] stopped on port 8000"
fi

if [ -n "$server_pids" ]; then
    echo "[status] related PID: $server_pids"
fi