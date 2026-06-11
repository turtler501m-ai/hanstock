from __future__ import annotations

import os
import sqlite3
from pathlib import Path


DEFAULT_BUSY_TIMEOUT_MS = 5_000


def _busy_timeout_ms() -> int:
    raw = os.environ.get("SQLITE_BUSY_TIMEOUT_MS", str(DEFAULT_BUSY_TIMEOUT_MS))
    try:
        return max(0, int(raw))
    except ValueError:
        return DEFAULT_BUSY_TIMEOUT_MS


def open_sqlite(
    path: str | Path,
    *,
    row_factory=None,
) -> sqlite3.Connection:
    db_path = Path(path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    timeout_ms = _busy_timeout_ms()
    conn = sqlite3.connect(
        db_path,
        timeout=timeout_ms / 1_000,
        check_same_thread=False,
    )
    conn.execute(f"PRAGMA busy_timeout={timeout_ms}")
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA foreign_keys=ON")
    if row_factory is not None:
        conn.row_factory = row_factory
    return conn
