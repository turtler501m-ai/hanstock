#!/usr/bin/env bash
# Continuous polling daemon - runs every 5 minutes
cd "$(dirname "$0")"

INTERVAL=300
LOG_FILE=".runtime/polld.log"

exec >> "$LOG_FILE" 2>&1

echo "$(date) polld started"

while true; do
    echo "$(date) polling..."
    POLLING_FORCE_RUN=1 ./poll.sh
    echo "$(date) done"
    sleep $INTERVAL
done