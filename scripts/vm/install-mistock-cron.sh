#!/bin/bash
# [유튜브 24편 구현] 미국주식 자동매매 크론 스케줄 등록기
set -euo pipefail

# US Market Hours (KST 기준 평일 밤 21:00 ~ 익일 새벽 05:59 사이 매 정각)
TIME_SPEC="${1:-0 21-23,0-5 * * 1-5}"
CRON_TZ_VALUE="${HANSTOCK_CRON_TZ:-Asia/Seoul}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
JOB="$TIME_SPEC cd $ROOT_DIR && $ROOT_DIR/scripts/vm/mistock-auto.sh"

existing="$(mktemp)"
crontab -l 2>/dev/null | awk '
    /# hanstock-mistock-auto begin/ { skip = 1; next }
    /# hanstock-mistock-auto end/ { skip = 0; next }
    skip != 1 { print }
' > "$existing" || true
{
    cat "$existing"
    echo "# hanstock-mistock-auto begin"
    echo "CRON_TZ=$CRON_TZ_VALUE"
    echo "$JOB"
    echo "# hanstock-mistock-auto end"
} | crontab -
rm -f "$existing"

echo "[cron] Mistock US stock schedule installed: CRON_TZ=$CRON_TZ_VALUE $JOB"
echo "[cron] current matching entries:"
crontab -l | awk '
    /# hanstock-mistock-auto begin/ { show = 1 }
    show == 1 { print }
    /# hanstock-mistock-auto end/ { show = 0 }
'
