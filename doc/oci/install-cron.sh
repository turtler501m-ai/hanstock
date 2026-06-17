#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="${1:-${OCI_RETRY_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}}"
ROOT_DIR="${ROOT_DIR/#\~/$HOME}"
mkdir -p "$ROOT_DIR"

CRON_TZ_VALUE="${OCI_RETRY_CRON_TZ:-Asia/Seoul}"
ATTEMPT_SPEC="${OCI_RETRY_ATTEMPT_CRON:-*/15 * * * *}"
REPORT_SPEC="${OCI_RETRY_REPORT_CRON:-0 18 * * *}"
LOCK_FILE="$ROOT_DIR/oci-retry.cron.lock"

tmp="$(mktemp)"
crontab -l 2>/dev/null | sed '/# OCI-VM-Retry start/,/# OCI-VM-Retry end/d' > "$tmp" || true
cat >> "$tmp" <<EOF
# OCI-VM-Retry start
CRON_TZ=$CRON_TZ_VALUE
$ATTEMPT_SPEC cd "$ROOT_DIR" && flock -n "$LOCK_FILE" "$ROOT_DIR/oci-retry.sh" >> "$ROOT_DIR/cron.log" 2>&1
$REPORT_SPEC cd "$ROOT_DIR" && "$ROOT_DIR/oci-report.sh" >> "$ROOT_DIR/report-cron.log" 2>&1
# OCI-VM-Retry end
EOF
crontab "$tmp"
rm -f "$tmp"

echo "[oci-cron] installed for $ROOT_DIR"
crontab -l | sed -n '/# OCI-VM-Retry start/,/# OCI-VM-Retry end/p'
