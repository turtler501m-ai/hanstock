#!/usr/bin/env bash
# Restart the local dashboard server in the current Git Bash terminal.

set -euo pipefail
cd "$(dirname "$0")"

PORT=${PORT:-8000}
RELOAD=${RELOAD:-true}

find_python() {
    if [ -n "${PYTHON:-}" ]; then
        printf '%s\n' "$PYTHON"
        return
    fi

    local local_app_data=""
    if [ -n "${LOCALAPPDATA:-}" ]; then
        if command -v cygpath >/dev/null 2>&1; then
            local_app_data=$(cygpath -u "$LOCALAPPDATA")
        else
            local_app_data=$LOCALAPPDATA
        fi
    fi

    for candidate in \
        ".venv/Scripts/python.exe" \
        "venv/Scripts/python.exe" \
        "$local_app_data/Programs/Python/Python314/python.exe" \
        "$local_app_data/Programs/Python/Python313/python.exe" \
        "$local_app_data/Programs/Python/Python312/python.exe" \
        "$local_app_data/Programs/Python/Python311/python.exe"; do
        if [ -n "${candidate:-}" ] && [ -x "$candidate" ]; then
            printf '%s\n' "$candidate"
            return
        fi
    done

    local resolved_python=""
    for candidate in python python3; do
        if command -v "$candidate" >/dev/null 2>&1; then
            resolved_python=$("$candidate" -c 'import sys; print(sys.executable)' 2>/dev/null | tr -d '\r' || true)
            if [ -n "$resolved_python" ] && [ -x "$resolved_python" ]; then
                printf '%s\n' "$resolved_python"
                return
            fi
        fi
    done

    if command -v py >/dev/null 2>&1; then
        resolved_python=$(py -3 -c 'import sys; print(sys.executable)' 2>/dev/null | tr -d '\r' || true)
        if [ -n "$resolved_python" ] && [ -x "$resolved_python" ]; then
            printf '%s\n' "$resolved_python"
            return
        fi
    fi

    echo "[restart] python executable not found" >&2
    exit 1
}

PYTHON_CMD=$(find_python)

if ! command -v powershell.exe >/dev/null 2>&1; then
    echo "[restart] powershell.exe was not found. Run this from Git Bash on Windows." >&2
    exit 1
fi

echo "[restart] stopping existing server on port ${PORT}..."
if command -v taskkill.exe >/dev/null 2>&1; then
    PIDS=$(
        powershell.exe -NoProfile -Command "\
            \$owners = Get-NetTCPConnection -State Listen -LocalPort ${PORT} -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique; \
            if (-not \$owners) { \
                netstat -ano | Select-String ':${PORT}\s+.*LISTENING\s+(\d+)' | ForEach-Object { \$_.Matches[0].Groups[1].Value } | Select-Object -Unique; \
            } else { \$owners }" 2>/dev/null \
        | tr -d '\r' \
        | grep -E '^[0-9]+$' || true
    )
    if [ -n "$PIDS" ]; then
        for PID in $PIDS; do
            powershell.exe -NoProfile -Command "Stop-Process -Id $PID -Force -ErrorAction Stop" >/dev/null 2>&1 \
                || taskkill.exe /PID "$PID" /F >/dev/null 2>&1 \
                || true
            if powershell.exe -NoProfile -Command "if (Get-Process -Id $PID -ErrorAction SilentlyContinue) { exit 1 }" >/dev/null 2>&1; then
                echo "[restart] stopped PID $PID"
            else
                echo "[restart] stop skipped PID $PID"
            fi
        done
    else
        echo "[restart] no listening server found"
    fi
else
    pkill -f "uvicorn src.dashboard" 2>/dev/null || true
fi

for _ in 1 2 3 4 5; do
    if powershell.exe -NoProfile -Command "if (Get-NetTCPConnection -State Listen -LocalPort ${PORT} -ErrorAction SilentlyContinue) { exit 1 }" >/dev/null 2>&1; then
        break
    fi
    sleep 1
done

CACHE=".runtime/candidate_snapshot.json"
if [ -f "$CACHE" ]; then
    rm "$CACHE"
    echo "[restart] removed cache: $CACHE"
fi

echo "[restart] starting server in this terminal -- http://localhost:${PORT}"
RELOAD_FLAG=""
[ "$RELOAD" = "true" ] && RELOAD_FLAG="--reload"

exec "$PYTHON_CMD" -m uvicorn src.dashboard:app $RELOAD_FLAG --host 127.0.0.1 --port "$PORT"
