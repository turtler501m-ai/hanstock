#!/bin/bash
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$SCRIPT_DIR"
cd "$ROOT_DIR" || exit 1
RUNTIME_DIR="$ROOT_DIR/.runtime"
PID_FILE="$RUNTIME_DIR/dashboard-server.pid"
STDOUT_LOG="$RUNTIME_DIR/dashboard-server.log"
STDERR_LOG="$RUNTIME_DIR/dashboard-server.err.log"

mkdir -p "$RUNTIME_DIR"

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

    echo "[start] python executable not found" >&2
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

listening_pids=$(get_listening_pids)

if [ -n "$listening_pids" ]; then
    echo "[start] already running on http://127.0.0.1:8000 (PID: $listening_pids)"
    exit 0
fi

python=$(find_python)
if [ $? -ne 0 ]; then
    exit 1
fi

echo "[start] starting server on http://127.0.0.1:8000"

nohup "$python" -m uvicorn src.dashboard:app --host 127.0.0.1 --port 8000 --reload \
    > "$STDOUT_LOG" 2> "$STDERR_LOG" &

new_pid=$!
echo "$new_pid" > "$PID_FILE"

echo "[start] started PID $new_pid -- http://127.0.0.1:8000"
echo "[start] stdout: $STDOUT_LOG"
echo "[start] stderr: $STDERR_LOG"

sleep 2
listening_pids=$(get_listening_pids)
if [ -n "$listening_pids" ]; then
    echo "[start] listening PID: $listening_pids"
else
    echo "[start] not listening yet; check logs with: ./logs.sh"
fi
