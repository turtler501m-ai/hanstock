# -*- coding: utf-8 -*-
"""AI스톡 전용 저장소 (§6).

테이블은 기존 메인 DB(`connect_db`)에 두고, 생성은 `repository.init_db()`가
`init_ai_stock_tables(conn)`을 호출하는 방식으로 연결한다(§6.0).
순환 import를 피하려고 `connect_db`는 함수 내에서 지연 import한다.

market 저장값은 KR/US만 허용하고 ALL은 거부한다(§6.0).
"""
from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone, timedelta
from typing import Any

from src.ai_stock.constants import SCAN_ACTIVE, SCAN_QUEUED, SCAN_RUNNING
from src.ai_stock.markets import require_storable_market
from src.ai_stock.schemas import dumps_json, loads_json

KST = timezone(timedelta(hours=9))


class ScanConflict(RuntimeError):
    """동일 (market, strategy_id) 활성 스캔 중복."""


def _now() -> str:
    return datetime.now(KST).isoformat()


def _connect():
    from src.db.repository import connect_db  # 지연 import (순환 방지)

    conn = connect_db()
    conn.row_factory = sqlite3.Row
    return conn


def _scan_stale_min() -> int:
    try:
        return max(1, int(os.environ.get("AI_STOCK_SCAN_STALE_MIN", "30")))
    except ValueError:
        return 30


# --------------------------------------------------------------------------- #
# 테이블 생성 (§6.1~6.8)
# --------------------------------------------------------------------------- #
def init_ai_stock_tables(conn) -> None:
    """repository.init_db()의 conn 컨텍스트 안에서 호출된다."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS ai_stock_scans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            market TEXT NOT NULL,
            strategy_id TEXT NOT NULL,
            strategy_version INTEGER,
            model TEXT,
            feature_version TEXT,
            prompt_version TEXT,
            profile_hash TEXT,
            status TEXT NOT NULL,
            started_at TEXT,
            completed_at TEXT,
            data_as_of TEXT,
            candidate_count INTEGER DEFAULT 0,
            fallback_count INTEGER DEFAULT 0,
            error_message TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS ai_stock_candidates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scan_id INTEGER NOT NULL,
            market TEXT NOT NULL,
            symbol TEXT NOT NULL,
            name TEXT,
            instrument_type TEXT DEFAULT 'stock',
            currency TEXT,
            current_price REAL,
            change_pct REAL,
            strategy_id TEXT,
            strategy_version INTEGER,
            model TEXT,
            feature_version TEXT,
            prompt_version TEXT,
            profile_hash TEXT,
            market_regime TEXT,
            rule_score REAL,
            technical_score REAL,
            momentum_score REAL,
            narrative_score REAL,
            ai_score REAL,
            risk_score REAL,
            final_score REAL,
            confidence REAL,
            decision TEXT,
            positive_factors TEXT,
            negative_factors TEXT,
            related_narratives TEXT,
            warnings TEXT,
            invalidation_conditions TEXT,
            data_quality TEXT,
            fallback_used INTEGER DEFAULT 0,
            fallback_reason TEXT,
            data_as_of TEXT,
            created_at TEXT
        )
        """
    )
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_ai_cand_unique ON ai_stock_candidates(scan_id, market, symbol)"
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS ai_stock_watchlist (
            candidate_id INTEGER PRIMARY KEY,
            market TEXT NOT NULL,
            symbol TEXT,
            status TEXT NOT NULL,
            initial_score REAL,
            current_score REAL,
            initial_price REAL,
            current_price REAL,
            related_narratives TEXT,
            market_regime TEXT,
            confirmation_conditions TEXT,
            invalidation_conditions TEXT,
            expires_at TEXT,
            rejection_reason TEXT,
            created_at TEXT,
            updated_at TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS ai_stock_watch_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            candidate_id INTEGER NOT NULL,
            ts TEXT NOT NULL,
            from_status TEXT,
            to_status TEXT,
            reason TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS ai_stock_performance (
            candidate_id INTEGER PRIMARY KEY,
            market TEXT,
            base_price REAL,
            base_date TEXT,
            price_1d REAL, return_1d REAL,
            price_5d REAL, return_5d REAL,
            price_20d REAL, return_20d REAL,
            mfe REAL, mae REAL,
            benchmark_return REAL,
            rule_only_result TEXT,
            actually_entered INTEGER DEFAULT 0,
            trade_id INTEGER,
            evaluation_complete INTEGER DEFAULT 0,
            updated_at TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS ai_stock_execution_plans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            candidate_id INTEGER,
            market TEXT NOT NULL,
            symbol TEXT,
            strategy_id TEXT,
            strategy_version INTEGER,
            action TEXT,
            entry_price REAL,
            stop_price REAL,
            take_profit REAL,
            risk_budget REAL,
            quantity INTEGER,
            estimated_cost REAL,
            safety_checks TEXT,
            status TEXT,
            approval_market TEXT,
            approval_db TEXT,
            approval_id INTEGER,
            approval_status TEXT,
            created_at TEXT,
            updated_at TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS ai_stock_automation_policies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            strategy_id TEXT NOT NULL,
            market TEXT NOT NULL,
            enabled INTEGER DEFAULT 1,
            automation_level INTEGER DEFAULT 4,
            auto_approve INTEGER DEFAULT 0,
            auto_execute INTEGER DEFAULT 0,
            max_daily_orders INTEGER DEFAULT 3,
            max_daily_loss_pct REAL DEFAULT 2.0,
            max_risk_per_trade_pct REAL DEFAULT 1.0,
            max_position_pct REAL DEFAULT 10.0,
            max_market_exposure_pct REAL DEFAULT 50.0,
            min_final_score REAL DEFAULT 65.0,
            min_rule_score REAL DEFAULT 40.0,
            max_risk_score REAL DEFAULT 60.0,
            allow_fallback_trade INTEGER DEFAULT 0,
            allow_stale_data_trade INTEGER DEFAULT 0,
            min_market_cap REAL,
            min_avg_trading_value REAL,
            min_price REAL,
            include_etf INTEGER DEFAULT 1,
            exclude_small_cap INTEGER DEFAULT 1,
            universe_source TEXT,
            excluded_types TEXT,
            briefing_freshness_min INTEGER DEFAULT 1440,
            timing_min_confidence REAL DEFAULT 0.6,
            realtime_poll_seconds INTEGER DEFAULT 5,
            created_at TEXT,
            updated_at TEXT
        )
        """
    )
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_ai_policy_unique ON ai_stock_automation_policies(strategy_id, market)"
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS ai_stock_execution_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            strategy_id TEXT,
            market TEXT,
            scan_id INTEGER,
            candidate_id INTEGER,
            plan_id INTEGER,
            run_type TEXT,
            automation_level INTEGER,
            status TEXT,
            blocked_stage TEXT,
            blocked_reason TEXT,
            policy_snapshot TEXT,
            safety_checks TEXT,
            approval_market TEXT,
            approval_db TEXT,
            approval_id INTEGER,
            order_id INTEGER,
            broker_order_id TEXT,
            started_at TEXT,
            completed_at TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS ai_stock_timing_signals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            strategy_id TEXT,
            market TEXT NOT NULL,
            candidate_id INTEGER NOT NULL,
            symbol TEXT,
            instrument_type TEXT,
            signal_type TEXT,
            trigger TEXT,
            ref_price REAL,
            signal_price REAL,
            ai_timing_confidence REAL,
            decision TEXT,
            blocked_reason TEXT,
            automation_level INTEGER,
            data_as_of TEXT,
            created_at TEXT
        )
        """
    )


# --------------------------------------------------------------------------- #
# 스캔 (§5.3·§6.1)
# --------------------------------------------------------------------------- #
def get_active_scan(market: str, strategy_id: str) -> dict[str, Any] | None:
    market = require_storable_market(market)
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM ai_stock_scans WHERE market=? AND strategy_id=? "
            "AND status IN (?, ?) ORDER BY id DESC LIMIT 1",
            (market, strategy_id, SCAN_QUEUED, SCAN_RUNNING),
        ).fetchone()
        if row is None:
            return None
        data = dict(row)
        # stale-running TTL 정리 (§6.1)
        from src.ai_stock.freshness import age_minutes

        age = age_minutes(data.get("started_at"))
        if age is not None and age > _scan_stale_min():
            conn.execute(
                "UPDATE ai_stock_scans SET status='failed', error_message=?, completed_at=? WHERE id=?",
                ("stale-running auto-cleanup", _now(), data["id"]),
            )
            conn.commit()
            return None
        return data


def create_scan(
    *,
    market: str,
    strategy_id: str,
    strategy_version: int | None = None,
    model: str | None = None,
    feature_version: str | None = None,
    prompt_version: str | None = None,
    profile_hash: str | None = None,
    data_as_of: str | None = None,
) -> int:
    """중복 활성 스캔이 있으면 ScanConflict (§5.3·§6.1)."""
    market = require_storable_market(market)
    now = _now()
    with _connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        active_rows = conn.execute(
            "SELECT id, started_at FROM ai_stock_scans WHERE market=? AND strategy_id=? "
            "AND status IN (?, ?)",
            (market, strategy_id, SCAN_QUEUED, SCAN_RUNNING),
        ).fetchall()
        stale_cutoff = datetime.now(KST) - timedelta(minutes=_scan_stale_min())
        for row in active_rows:
            started_at = None
            try:
                started_at = datetime.fromisoformat(str(row["started_at"]).replace("Z", "+00:00"))
            except Exception:
                pass
            if started_at and started_at.tzinfo is None:
                started_at = started_at.replace(tzinfo=KST)
            if started_at is not None and started_at < stale_cutoff:
                conn.execute(
                    "UPDATE ai_stock_scans SET status='failed', error_message=?, completed_at=? WHERE id=?",
                    ("stale-running auto-cleanup", now, row["id"]),
                )
        active = conn.execute(
            "SELECT id FROM ai_stock_scans WHERE market=? AND strategy_id=? "
            "AND status IN (?, ?) ORDER BY id DESC LIMIT 1",
            (market, strategy_id, SCAN_QUEUED, SCAN_RUNNING),
        ).fetchone()
        if active is not None:
            conn.execute("ROLLBACK")
            raise ScanConflict(f"active scan exists for ({market}, {strategy_id})")
        cur = conn.execute(
            "INSERT INTO ai_stock_scans (market, strategy_id, strategy_version, model, "
            "feature_version, prompt_version, profile_hash, status, started_at, data_as_of) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (market, strategy_id, strategy_version, model, feature_version,
             prompt_version, profile_hash, SCAN_RUNNING, now, data_as_of),
        )
        conn.commit()
        return int(cur.lastrowid)


def finish_scan(scan_id: int, *, status: str, candidate_count: int = 0,
                fallback_count: int = 0, error_message: str | None = None) -> None:
    with _connect() as conn:
        conn.execute(
            "UPDATE ai_stock_scans SET status=?, completed_at=?, candidate_count=?, "
            "fallback_count=?, error_message=? WHERE id=?",
            (status, _now(), candidate_count, fallback_count, error_message, scan_id),
        )
        conn.commit()


def get_scan(scan_id: int) -> dict[str, Any] | None:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM ai_stock_scans WHERE id=?", (scan_id,)).fetchone()
        return dict(row) if row else None


def list_scans(market: str | None = None, limit: int = 20) -> list[dict[str, Any]]:
    limit = max(1, min(int(limit or 20), 200))
    with _connect() as conn:
        if market and str(market).upper() != "ALL":
            rows = conn.execute(
                "SELECT * FROM ai_stock_scans WHERE market=? ORDER BY id DESC LIMIT ?",
                (require_storable_market(market), limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM ai_stock_scans ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(r) for r in rows]


# --------------------------------------------------------------------------- #
# 후보 (§5.3·§6.2)
# --------------------------------------------------------------------------- #
_CAND_JSON_FIELDS = (
    "positive_factors", "negative_factors", "related_narratives",
    "warnings", "invalidation_conditions",
)


def save_candidate(candidate: dict[str, Any]) -> int:
    market = require_storable_market(candidate.get("market"))
    row = dict(candidate)
    row["market"] = market
    row.setdefault("created_at", _now())
    for f in _CAND_JSON_FIELDS:
        row[f] = dumps_json(row.get(f) or [])
    row["fallback_used"] = 1 if row.get("fallback_used") else 0
    cols = [
        "scan_id", "market", "symbol", "name", "instrument_type", "currency",
        "current_price", "change_pct", "strategy_id", "strategy_version", "model",
        "feature_version", "prompt_version", "profile_hash", "market_regime",
        "rule_score", "technical_score", "momentum_score", "narrative_score",
        "ai_score", "risk_score", "final_score", "confidence", "decision",
        "positive_factors", "negative_factors", "related_narratives", "warnings",
        "invalidation_conditions", "data_quality", "fallback_used", "fallback_reason",
        "data_as_of", "created_at",
    ]
    placeholders = ", ".join(["?"] * len(cols))
    with _connect() as conn:
        cur = conn.execute(
            f"INSERT OR REPLACE INTO ai_stock_candidates ({', '.join(cols)}) VALUES ({placeholders})",
            tuple(row.get(c) for c in cols),
        )
        conn.commit()
        return int(cur.lastrowid)


def _candidate_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    d = dict(row)
    d["scan_id"] = d.pop("id", None) if False else d.get("scan_id")
    d["candidate_id"] = row["id"]
    for f in _CAND_JSON_FIELDS:
        d[f] = loads_json(d.get(f), [])
    d["fallback_used"] = bool(d.get("fallback_used"))
    return d


def list_candidates(
    *, market: str | None = None, scan_id: int | None = None,
    decision: str | None = None, min_score: float | None = None, limit: int = 100,
) -> list[dict[str, Any]]:
    limit = max(1, min(int(limit or 100), 500))
    where, params = [], []
    if market and str(market).upper() != "ALL":
        where.append("market=?")
        params.append(require_storable_market(market))
    if scan_id is not None:
        where.append("scan_id=?")
        params.append(int(scan_id))
    if decision:
        where.append("decision=?")
        params.append(str(decision))
    if min_score is not None:
        where.append("final_score >= ?")
        params.append(float(min_score))
    clause = ("WHERE " + " AND ".join(where)) if where else ""
    params.append(limit)
    with _connect() as conn:
        rows = conn.execute(
            f"SELECT * FROM ai_stock_candidates {clause} ORDER BY final_score DESC, symbol LIMIT ?",
            tuple(params),
        ).fetchall()
        return [_candidate_to_dict(r) for r in rows]


def get_candidate(candidate_id: int) -> dict[str, Any] | None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM ai_stock_candidates WHERE id=?", (int(candidate_id),)
        ).fetchone()
        return _candidate_to_dict(row) if row else None


# --------------------------------------------------------------------------- #
# 관찰종목 (§5.5·§6.3)
# --------------------------------------------------------------------------- #
_WATCH_JSON_FIELDS = ("related_narratives", "confirmation_conditions", "invalidation_conditions")


def upsert_watch(candidate_id: int, data: dict[str, Any]) -> None:
    row = dict(data)
    row["candidate_id"] = int(candidate_id)
    row["market"] = require_storable_market(row.get("market"))
    row.setdefault("created_at", _now())
    row["updated_at"] = _now()
    for f in _WATCH_JSON_FIELDS:
        row[f] = dumps_json(row.get(f) or [])
    cols = [
        "candidate_id", "market", "symbol", "status", "initial_score", "current_score",
        "initial_price", "current_price", "related_narratives", "market_regime",
        "confirmation_conditions", "invalidation_conditions", "expires_at",
        "rejection_reason", "created_at", "updated_at",
    ]
    placeholders = ", ".join(["?"] * len(cols))
    with _connect() as conn:
        conn.execute(
            f"INSERT OR REPLACE INTO ai_stock_watchlist ({', '.join(cols)}) VALUES ({placeholders})",
            tuple(row.get(c) for c in cols),
        )
        conn.commit()


def get_watch(candidate_id: int) -> dict[str, Any] | None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM ai_stock_watchlist WHERE candidate_id=?", (int(candidate_id),)
        ).fetchone()
        if not row:
            return None
        d = dict(row)
        for f in _WATCH_JSON_FIELDS:
            d[f] = loads_json(d.get(f), [])
        return d


def list_watchlist(market: str | None = None, status: str | None = None) -> list[dict[str, Any]]:
    where, params = [], []
    if market and str(market).upper() != "ALL":
        where.append("market=?")
        params.append(require_storable_market(market))
    if status:
        where.append("status=?")
        params.append(str(status))
    clause = ("WHERE " + " AND ".join(where)) if where else ""
    with _connect() as conn:
        rows = conn.execute(
            f"SELECT * FROM ai_stock_watchlist {clause} ORDER BY updated_at DESC", tuple(params)
        ).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            for f in _WATCH_JSON_FIELDS:
                d[f] = loads_json(d.get(f), [])
            out.append(d)
        return out


def update_watch_status(candidate_id: int, to_status: str, *, reason: str | None = None) -> None:
    with _connect() as conn:
        cur = conn.execute(
            "SELECT status FROM ai_stock_watchlist WHERE candidate_id=?", (int(candidate_id),)
        ).fetchone()
        from_status = cur["status"] if cur else None
        conn.execute(
            "UPDATE ai_stock_watchlist SET status=?, rejection_reason=COALESCE(?, rejection_reason), updated_at=? WHERE candidate_id=?",
            (to_status, reason, _now(), int(candidate_id)),
        )
        conn.execute(
            "INSERT INTO ai_stock_watch_events (candidate_id, ts, from_status, to_status, reason) VALUES (?, ?, ?, ?, ?)",
            (int(candidate_id), _now(), from_status, to_status, reason),
        )
        conn.commit()


def remove_watch(candidate_id: int) -> None:
    with _connect() as conn:
        conn.execute("DELETE FROM ai_stock_watchlist WHERE candidate_id=?", (int(candidate_id),))
        conn.commit()


def list_watch_events(candidate_id: int) -> list[dict[str, Any]]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM ai_stock_watch_events WHERE candidate_id=? ORDER BY id DESC",
            (int(candidate_id),),
        ).fetchall()
        return [dict(r) for r in rows]


# --------------------------------------------------------------------------- #
# 자동화 정책 (§6.6)
# --------------------------------------------------------------------------- #
def get_policy(strategy_id: str, market: str) -> dict[str, Any] | None:
    market = require_storable_market(market)
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM ai_stock_automation_policies WHERE strategy_id=? AND market=?",
            (strategy_id, market),
        ).fetchone()
        return dict(row) if row else None


def upsert_policy(strategy_id: str, market: str, fields: dict[str, Any]) -> dict[str, Any]:
    market = require_storable_market(market)
    existing = get_policy(strategy_id, market)
    now = _now()
    allowed = {
        "enabled", "automation_level", "auto_approve", "auto_execute", "max_daily_orders",
        "max_daily_loss_pct", "max_risk_per_trade_pct", "max_position_pct",
        "max_market_exposure_pct", "min_final_score", "min_rule_score", "max_risk_score",
        "allow_fallback_trade", "allow_stale_data_trade",
        "min_market_cap", "min_avg_trading_value", "min_price", "include_etf",
        "exclude_small_cap", "universe_source", "excluded_types",
        "briefing_freshness_min", "timing_min_confidence", "realtime_poll_seconds",
    }
    data = {k: v for k, v in (fields or {}).items() if k in allowed}
    with _connect() as conn:
        if existing:
            sets = ", ".join(f"{k}=?" for k in data) + (", " if data else "") + "updated_at=?"
            conn.execute(
                f"UPDATE ai_stock_automation_policies SET {sets} WHERE strategy_id=? AND market=?",
                (*data.values(), now, strategy_id, market),
            )
        else:
            cols = ["strategy_id", "market", *data.keys(), "created_at", "updated_at"]
            vals = [strategy_id, market, *data.values(), now, now]
            conn.execute(
                f"INSERT INTO ai_stock_automation_policies ({', '.join(cols)}) "
                f"VALUES ({', '.join(['?'] * len(cols))})",
                tuple(vals),
            )
        conn.commit()
    return get_policy(strategy_id, market)


def list_policies(market: str | None = None) -> list[dict[str, Any]]:
    with _connect() as conn:
        if market and str(market).upper() != "ALL":
            rows = conn.execute(
                "SELECT * FROM ai_stock_automation_policies WHERE market=? ORDER BY strategy_id",
                (require_storable_market(market),),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM ai_stock_automation_policies ORDER BY market, strategy_id"
            ).fetchall()
        return [dict(r) for r in rows]


# --------------------------------------------------------------------------- #
# 성과 / 실행 계획 / 실행 이력 / 타이밍 신호
# --------------------------------------------------------------------------- #
def save_performance(candidate_id: int, data: dict[str, Any]) -> None:
    row = dict(data)
    row["candidate_id"] = int(candidate_id)
    row["updated_at"] = _now()
    if "rule_only_result" in row:
        row["rule_only_result"] = dumps_json(row.get("rule_only_result"))
    cols = [
        "candidate_id", "market", "base_price", "base_date", "price_1d", "return_1d",
        "price_5d", "return_5d", "price_20d", "return_20d", "mfe", "mae",
        "benchmark_return", "rule_only_result", "actually_entered", "trade_id",
        "evaluation_complete", "updated_at",
    ]
    with _connect() as conn:
        conn.execute(
            f"INSERT OR REPLACE INTO ai_stock_performance ({', '.join(cols)}) "
            f"VALUES ({', '.join(['?'] * len(cols))})",
            tuple(row.get(c) for c in cols),
        )
        conn.commit()


def list_performance(market: str | None = None, limit: int = 200) -> list[dict[str, Any]]:
    with _connect() as conn:
        if market and str(market).upper() != "ALL":
            rows = conn.execute(
                "SELECT * FROM ai_stock_performance WHERE market=? ORDER BY updated_at DESC LIMIT ?",
                (require_storable_market(market), int(limit)),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM ai_stock_performance ORDER BY updated_at DESC LIMIT ?", (int(limit),)
            ).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["rule_only_result"] = loads_json(d.get("rule_only_result"), {})
            out.append(d)
        return out


def save_execution_plan(plan: dict[str, Any]) -> int:
    row = dict(plan)
    row["market"] = require_storable_market(row.get("market"))
    row.setdefault("created_at", _now())
    row["updated_at"] = _now()
    if "safety_checks" in row:
        row["safety_checks"] = dumps_json(row.get("safety_checks"))
    cols = [
        "candidate_id", "market", "symbol", "strategy_id", "strategy_version", "action",
        "entry_price", "stop_price", "take_profit", "risk_budget", "quantity",
        "estimated_cost", "safety_checks", "status", "approval_market", "approval_db",
        "approval_id", "approval_status", "created_at", "updated_at",
    ]
    with _connect() as conn:
        cur = conn.execute(
            f"INSERT INTO ai_stock_execution_plans ({', '.join(cols)}) "
            f"VALUES ({', '.join(['?'] * len(cols))})",
            tuple(row.get(c) for c in cols),
        )
        conn.commit()
        return int(cur.lastrowid)


def list_execution_plans(market: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
    with _connect() as conn:
        if market and str(market).upper() != "ALL":
            rows = conn.execute(
                "SELECT * FROM ai_stock_execution_plans WHERE market=? ORDER BY id DESC LIMIT ?",
                (require_storable_market(market), int(limit)),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM ai_stock_execution_plans ORDER BY id DESC LIMIT ?", (int(limit),)
            ).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["safety_checks"] = loads_json(d.get("safety_checks"), [])
            out.append(d)
        return out


def get_execution_plan(plan_id: int) -> dict[str, Any] | None:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM ai_stock_execution_plans WHERE id=?", (int(plan_id),)).fetchone()
        if not row:
            return None
        d = dict(row)
        d["safety_checks"] = loads_json(d.get("safety_checks"), [])
        return d


def update_execution_plan_approval(
    plan_id: int,
    *,
    approval_market: str,
    approval_db: str,
    approval_id: int,
    approval_status: str = "pending",
) -> None:
    with _connect() as conn:
        conn.execute(
            """
            UPDATE ai_stock_execution_plans
            SET approval_market=?, approval_db=?, approval_id=?, approval_status=?,
                status=?, updated_at=?
            WHERE id=?
            """,
            (
                require_storable_market(approval_market),
                approval_db,
                int(approval_id),
                approval_status,
                "approval_queued",
                _now(),
                int(plan_id),
            ),
        )
        conn.commit()


def update_execution_plan_status(
    plan_id: int,
    *,
    status: str,
    approval_status: str | None = None,
) -> None:
    fields = {"status": status, "updated_at": _now()}
    if approval_status is not None:
        fields["approval_status"] = approval_status
    sets = ", ".join(f"{k}=?" for k in fields)
    with _connect() as conn:
        conn.execute(
            f"UPDATE ai_stock_execution_plans SET {sets} WHERE id=?",
            (*fields.values(), int(plan_id)),
        )
        conn.commit()


def log_execution_run(data: dict[str, Any]) -> int:
    row = dict(data)
    row.setdefault("started_at", _now())
    for f in ("policy_snapshot", "safety_checks"):
        if f in row:
            row[f] = dumps_json(row.get(f))
    cols = [
        "strategy_id", "market", "scan_id", "candidate_id", "plan_id", "run_type",
        "automation_level", "status", "blocked_stage", "blocked_reason",
        "policy_snapshot", "safety_checks", "approval_market", "approval_db",
        "approval_id", "order_id", "broker_order_id", "started_at", "completed_at",
    ]
    with _connect() as conn:
        cur = conn.execute(
            f"INSERT INTO ai_stock_execution_runs ({', '.join(cols)}) "
            f"VALUES ({', '.join(['?'] * len(cols))})",
            tuple(row.get(c) for c in cols),
        )
        conn.commit()
        return int(cur.lastrowid)


def list_execution_runs(market: str | None = None, strategy_id: str | None = None,
                        limit: int = 100) -> list[dict[str, Any]]:
    where, params = [], []
    if market and str(market).upper() != "ALL":
        where.append("market=?")
        params.append(require_storable_market(market))
    if strategy_id:
        where.append("strategy_id=?")
        params.append(strategy_id)
    clause = ("WHERE " + " AND ".join(where)) if where else ""
    params.append(int(limit))
    with _connect() as conn:
        rows = conn.execute(
            f"SELECT * FROM ai_stock_execution_runs {clause} ORDER BY id DESC LIMIT ?", tuple(params)
        ).fetchall()
        return [dict(r) for r in rows]


def save_timing_signal(signal: dict[str, Any]) -> int:
    row = dict(signal)
    row["market"] = require_storable_market(row.get("market"))
    row.setdefault("created_at", _now())
    cols = [
        "strategy_id", "market", "candidate_id", "symbol", "instrument_type",
        "signal_type", "trigger", "ref_price", "signal_price", "ai_timing_confidence",
        "decision", "blocked_reason", "automation_level", "data_as_of", "created_at",
    ]
    with _connect() as conn:
        cur = conn.execute(
            f"INSERT INTO ai_stock_timing_signals ({', '.join(cols)}) "
            f"VALUES ({', '.join(['?'] * len(cols))})",
            tuple(row.get(c) for c in cols),
        )
        conn.commit()
        return int(cur.lastrowid)


def list_timing_signals(market: str | None = None, candidate_id: int | None = None,
                        limit: int = 100) -> list[dict[str, Any]]:
    where, params = [], []
    if market and str(market).upper() != "ALL":
        where.append("market=?")
        params.append(require_storable_market(market))
    if candidate_id is not None:
        where.append("candidate_id=?")
        params.append(int(candidate_id))
    clause = ("WHERE " + " AND ".join(where)) if where else ""
    params.append(int(limit))
    with _connect() as conn:
        rows = conn.execute(
            f"SELECT * FROM ai_stock_timing_signals {clause} ORDER BY id DESC LIMIT ?", tuple(params)
        ).fetchall()
        return [dict(r) for r in rows]
