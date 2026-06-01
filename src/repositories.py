from __future__ import annotations

from dataclasses import dataclass
import sqlite3
from typing import Callable


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, column_type: str) -> None:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    existing = {row[1] for row in rows}
    if column not in existing:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {column_type}")


@dataclass(frozen=True)
class ApprovalRecord:
    id: int
    created_at: str
    updated_at: str
    symbol: str
    name: str
    action: str
    qty: int
    price: int
    reason: str
    source: str
    status: str
    response_msg: str
    strategy_id: str = ""
    strategy_version: int | None = None
    profile_hash: str = ""
    source_candidate_id: int | None = None


def _approval_record_from_row(row: sqlite3.Row) -> ApprovalRecord:
    return ApprovalRecord(
        id=int(row["id"]),
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
        symbol=str(row["symbol"]),
        name=str(row["name"]),
        action=str(row["action"]),
        qty=int(row["qty"]),
        price=int(row["price"]),
        reason=str(row["reason"] or ""),
        source=str(row["source"] or ""),
        status=str(row["status"]),
        response_msg=str(row["response_msg"] or ""),
        strategy_id=str(row["strategy_id"] or "") if "strategy_id" in row.keys() else "",
        strategy_version=int(row["strategy_version"]) if "strategy_version" in row.keys() and row["strategy_version"] is not None else None,
        profile_hash=str(row["profile_hash"] or "") if "profile_hash" in row.keys() else "",
        source_candidate_id=int(row["source_candidate_id"]) if "source_candidate_id" in row.keys() and row["source_candidate_id"] is not None else None,
    )


class ApprovalRepository:
    def __init__(self, connect_fn: Callable[[], sqlite3.Connection]) -> None:
        self._connect_fn = connect_fn

    def init_db(self) -> None:
        conn = self._connect_fn()
        try:
            with conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS approvals (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        symbol TEXT NOT NULL,
                        name TEXT NOT NULL,
                        action TEXT NOT NULL,
                        qty INTEGER NOT NULL,
                        price INTEGER NOT NULL,
                        reason TEXT,
                        source TEXT,
                        status TEXT NOT NULL,
                        response_msg TEXT
                    )
                    """
                )
                _ensure_column(conn, "approvals", "strategy_id", "TEXT")
                _ensure_column(conn, "approvals", "strategy_version", "INTEGER")
                _ensure_column(conn, "approvals", "profile_hash", "TEXT")
                _ensure_column(conn, "approvals", "source_candidate_id", "INTEGER")
        finally:
            conn.close()

    def create_approval(
        self,
        *,
        created_at: str,
        updated_at: str,
        symbol: str,
        name: str,
        action: str,
        qty: int,
        price: int,
        reason: str,
        source: str,
        status: str = "pending",
        response_msg: str = "",
        strategy_id: str = "",
        strategy_version: int | None = None,
        profile_hash: str = "",
        source_candidate_id: int | None = None,
    ) -> int:
        conn = self._connect_fn()
        try:
            with conn:
                cursor = conn.execute(
                    """
                    INSERT INTO approvals
                    (
                        created_at, updated_at, symbol, name, action, qty, price, reason, source,
                        status, response_msg, strategy_id, strategy_version, profile_hash, source_candidate_id
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        created_at,
                        updated_at,
                        symbol,
                        name,
                        action,
                        qty,
                        price,
                        reason,
                        source,
                        status,
                        response_msg,
                        strategy_id,
                        strategy_version,
                        profile_hash,
                        source_candidate_id,
                    ),
                )
                return int(cursor.lastrowid)
        finally:
            conn.close()

    def get_approval(self, approval_id: int) -> ApprovalRecord | None:
        conn = self._connect_fn()
        try:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM approvals WHERE id = ?",
                (approval_id,),
            ).fetchone()
        finally:
            conn.close()
        if row is None:
            return None
        return _approval_record_from_row(row)

    def list_approvals(self, *, limit: int) -> list[ApprovalRecord]:
        conn = self._connect_fn()
        try:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM approvals ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        finally:
            conn.close()
        return [_approval_record_from_row(row) for row in rows]

    def update_approval_status(
        self,
        approval_id: int,
        *,
        status: str,
        response_msg: str,
        updated_at: str,
    ) -> bool:
        conn = self._connect_fn()
        try:
            with conn:
                cursor = conn.execute(
                    """
                    UPDATE approvals
                    SET status = ?, response_msg = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (status, response_msg, updated_at, approval_id),
                )
                return cursor.rowcount > 0
        finally:
            conn.close()
