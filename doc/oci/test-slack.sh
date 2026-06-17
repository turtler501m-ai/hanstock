#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="${OCI_RETRY_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}"
cd "$ROOT_DIR"
if [ -d "$ROOT_DIR/.venv/bin" ]; then
  export PATH="$ROOT_DIR/.venv/bin:$PATH"
fi

exec python3 "$ROOT_DIR/oci_retry.py" test-slack --root "$ROOT_DIR" "$@"
