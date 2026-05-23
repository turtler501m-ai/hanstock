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

pids=$(get_server_pids)

if [ -z "$pids" ]; then
    echo "[stop] no dashboard server found on port 8000"
    [ -f "$PID_FILE" ] && rm -f "$PID_FILE"
    exit 0
fi

for pid in $pids; do
    if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
        kill "$pid" 2>/dev/null && echo "[stop] stopped PID $pid" || echo "[stop] stop skipped PID $pid"
    fi
done

[ -f "$PID_FILE" ] && rm -f "$PID_FILE"
echo "[stop] server stopped"