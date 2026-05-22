#!/bin/bash
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$SCRIPT_DIR"
RUNTIME_DIR="$ROOT_DIR/.runtime"
PID_FILE="$RUNTIME_DIR/dashboard-server.pid"
STDOUT_LOG="$RUNTIME_DIR/dashboard-server.log"
STDERR_LOG="$RUNTIME_DIR/dashboard-server.err.log"

find_python() {
    if [ -n "${PYTHON:-}" ]; then
        echo "$PYTHON"
        return 0
    fi

    if [ -x "$ROOT_DIR/.venv/bin/python" ]; then
        echo "$ROOT_DIR/.venv/bin/python"
        return 0
    fi

    if [ -x "$ROOT_DIR/venv/bin/python" ]; then
        echo "$ROOT_DIR/venv/bin/python"
        return 0
    fi

    for candidate in python3 python; do
        if command -v "$candidate" >/dev/null 2>&1; then
            echo "$(command -v "$candidate")"
            return 0
        fi
    done

    echo "[restart] python executable not found" >&2
    return 1
}

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

echo "[restart] stopping existing server on port 8000..."
pids=$(get_server_pids)

if [ -n "$pids" ]; then
    for pid in $pids; do
        if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
            kill "$pid" 2>/dev/null && echo "[restart] stopped PID $pid" || true
        fi
    done
else
    echo "[restart] no running server found"
fi

[ -f "$PID_FILE" ] && rm -f "$PID_FILE"

for _ in 1 2 3 4 5; do
    listening_pids=$(get_listening_pids)
    if [ -z "$listening_pids" ]; then
        break
    fi
    sleep 1
done

python=$(find_python)
if [ $? -ne 0 ]; then
    exit 1
fi

mkdir -p "$ROOT_DIR/logs"

echo "[restart] starting server -- http://0.0.0.0:8000"

# 텔레그램 폴링 프로세스 정리 후 백그라운드 재시작
pkill -f "poll\.py" 2>/dev/null || true

nohup "$python" "$ROOT_DIR/src/futures_signals/poll.py" \
    > "$ROOT_DIR/logs/poll.log" 2>&1 &
POLL_PID=$!
echo "[restart] poll.py started: PID=$POLL_PID"

# 대시보드 시작 (포그라운드, exec로 프로세스 교체)
exec "$python" -m uvicorn src.dashboard:app --reload --host 127.0.0.1 --port 8000 \
    >> "$ROOT_DIR/logs/dashboard.log" 2>&1