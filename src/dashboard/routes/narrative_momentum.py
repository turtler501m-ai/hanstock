# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Body, HTTPException
from fastapi.responses import FileResponse

from src import trader
from src.dashboard.core import WEB_DIR
from src.db.repository import init_db, save_scanned_candidate
from src.strategy.narrative_momentum import (
    STRATEGY_ID,
    NarrativeMomentumSettings,
    NarrativeMomentumStrategy,
    load_json_file,
    save_json_file,
)
from src.utils.logger import logger

router = APIRouter(tags=["narrative-momentum"])

BASE_DIR = Path(__file__).resolve().parents[3]
THEME_MAP_PATH = BASE_DIR / "config" / "theme_map.json"
NARRATIVE_HISTORY_PATH = BASE_DIR / ".runtime" / "narrative_history.json"
LATEST_RESULT_PATH = BASE_DIR / ".runtime" / "narrative_momentum_latest.json"


@router.get("/narrative-momentum", response_class=FileResponse)
def read_narrative_momentum_dashboard():
    return FileResponse(WEB_DIR / "templates" / "narrative_momentum.html")


@router.get("/api/narrative-momentum/status")
def get_narrative_momentum_status():
    history, theme_map, errors = _load_inputs()
    strategy = _strategy()
    status = strategy.status(history, theme_map)
    signals = strategy.calculate_signals(history, theme_map)
    unmatched = strategy.unmatched_narratives(history, theme_map)
    status.update(
        {
            "ok": not errors,
            "errors": errors,
            "strategy_id": STRATEGY_ID,
            "candidate_count": len(signals),
            "unmatched_count": len(unmatched),
            "latest_result_path": _display_path(LATEST_RESULT_PATH),
            "history_path": _display_path(NARRATIVE_HISTORY_PATH),
            "theme_map_path": _display_path(THEME_MAP_PATH),
            "safety": {
                "dry_run": bool(trader.DRY_RUN),
                "trading_env": trader.TRADING_ENV,
                "enable_live_trading": bool(trader.ENABLE_LIVE_TRADING),
                "require_approval": bool(trader.REQUIRE_APPROVAL),
                "online_access_blocked": bool(getattr(trader.config, "online_access_blocked", False)),
            },
        }
    )
    return status


@router.get("/api/narrative-momentum/latest")
def get_narrative_momentum_latest():
    history, theme_map, errors = _load_inputs()
    strategy = _strategy()
    status = strategy.status(history, theme_map)
    signals = strategy.calculate_signals(history, theme_map)
    unmatched = strategy.unmatched_narratives(history, theme_map)
    payload = {
        "ok": not errors,
        "errors": errors,
        "strategy_id": STRATEGY_ID,
        "status": status,
        "signals": signals,
        "unmatched": unmatched,
        "total_scanned": len(signals),
    }
    return payload


@router.post("/api/narrative-momentum/scan")
def scan_narrative_momentum(payload: dict | None = Body(default=None)):
    history, theme_map, errors = _load_inputs()
    if errors:
        raise HTTPException(status_code=400, detail="; ".join(errors))
    strategy = _strategy()
    status = strategy.status(history, theme_map)
    signals = strategy.calculate_signals(history, theme_map)
    result = {
        "strategy": STRATEGY_ID,
        "status": status,
        "signals": signals,
        "total_scanned": len(signals),
        "saved_count": 0,
    }
    if payload and payload.get("save_candidates"):
        result["saved_count"] = _save_candidates(signals)
    save_json_file(LATEST_RESULT_PATH, result)
    return result


@router.get("/api/narrative-momentum/history")
def get_narrative_momentum_history(limit: int = 20):
    history = load_json_file(NARRATIVE_HISTORY_PATH, [])
    if not isinstance(history, list):
        raise HTTPException(status_code=400, detail="narrative_history must be a list")
    rows = sorted([row for row in history if isinstance(row, dict)], key=lambda item: str(item.get("date") or ""), reverse=True)
    return {"history": rows[: max(1, min(limit, 100))], "count": len(rows)}


@router.post("/api/narrative-momentum/history")
def save_narrative_momentum_history(payload: dict = Body(...)):
    history = payload.get("history")
    if not isinstance(history, list):
        raise HTTPException(status_code=400, detail="history must be a list")
    for entry in history:
        if not isinstance(entry, dict):
            raise HTTPException(status_code=400, detail="each history entry must be an object")
        if not str(entry.get("date") or "").strip():
            raise HTTPException(status_code=400, detail="each history entry requires date")
        narratives = entry.get("dominant_narratives", [])
        if not isinstance(narratives, list):
            raise HTTPException(status_code=400, detail="dominant_narratives must be a list")
    save_json_file(NARRATIVE_HISTORY_PATH, history)
    return {"ok": True, "count": len(history), "path": _display_path(NARRATIVE_HISTORY_PATH)}


@router.get("/api/narrative-momentum/theme-map")
def get_narrative_theme_map():
    theme_map = load_json_file(THEME_MAP_PATH, {})
    if not isinstance(theme_map, dict):
        raise HTTPException(status_code=400, detail="theme_map must be an object")
    themes = []
    for theme, stocks in sorted(theme_map.items()):
        stock_rows = stocks if isinstance(stocks, list) else []
        themes.append(
            {
                "theme": theme,
                "stock_count": len(stock_rows),
                "stocks": stock_rows,
            }
        )
    return {"themes": themes, "count": len(themes)}


@router.post("/api/narrative-momentum/theme-map/reload")
def reload_narrative_theme_map():
    return get_narrative_theme_map()


@router.post("/api/narrative-momentum/queue-approval")
def queue_narrative_approval(payload: dict = Body(...)):
    ticker = str(payload.get("ticker") or payload.get("symbol") or "").strip()
    if not ticker:
        raise HTTPException(status_code=400, detail="ticker is required")
    name = str(payload.get("name") or ticker)
    settings = NarrativeMomentumSettings()

    history, theme_map, errors = _load_inputs()
    if errors:
        raise HTTPException(status_code=400, detail="; ".join(errors))
    strategy = _strategy()
    status = strategy.status(history, theme_map)
    if status.get("state") != "fresh":
        raise HTTPException(status_code=409, detail="fresh narrative data is required")
    signals = strategy.calculate_signals(history, theme_map)
    signal = next((item for item in signals if str(item.get("ticker")) == ticker), None)
    if signal is None:
        raise HTTPException(status_code=404, detail="ticker is not in current narrative signals")
    server_score = _to_float(signal.get("final_score"))
    if server_score < settings.approval_score_min:
        raise HTTPException(status_code=400, detail=f"server score must be >= {settings.approval_score_min:g}")
    if _has_pending_buy(ticker):
        raise HTTPException(status_code=409, detail="pending buy approval already exists")

    qty = int(_to_float(payload.get("qty")))
    price = int(_to_float(payload.get("price")) or 0)
    if qty <= 0:
        raise HTTPException(status_code=400, detail="qty must be greater than 0")
    if price <= 0:
        raise HTTPException(status_code=400, detail="price must be greater than 0")
    name = str(signal.get("name") or name)
    reason = f"내러티브 모멘텀 {server_score:g}점: {', '.join(signal.get('narratives', [])[:2])}"
    client_reason = str(payload.get("reason") or "").strip()
    if client_reason:
        reason = f"{reason} / 요청메모: {client_reason[:120]}"
    approval_id = _create_approval_row(
        {
            "symbol": ticker,
            "name": name,
            "action": "buy",
            "qty": qty,
            "price": price,
            "reason": reason,
            "source": "narrative_momentum",
            "strategy_id": STRATEGY_ID,
        }
    )
    return {"ok": True, "id": approval_id, "status": "pending"}


def _strategy() -> NarrativeMomentumStrategy:
    return NarrativeMomentumStrategy()


def _load_inputs() -> tuple[list[dict[str, Any]], dict[str, list[dict[str, Any]]], list[str]]:
    errors = []
    try:
        history = load_json_file(NARRATIVE_HISTORY_PATH, [])
    except (json.JSONDecodeError, OSError, TypeError) as exc:
        history = []
        errors.append(f"failed to load narrative history: {exc}")
    try:
        theme_map = load_json_file(THEME_MAP_PATH, {})
    except (json.JSONDecodeError, OSError, TypeError) as exc:
        theme_map = {}
        errors.append(f"failed to load theme map: {exc}")
    if not isinstance(history, list):
        errors.append("narrative_history must be a list")
        history = []
    if not isinstance(theme_map, dict):
        errors.append("theme_map must be an object")
        theme_map = {}
    return history, theme_map, errors


def _save_candidates(signals: list[dict[str, Any]]) -> int:
    saved_count = 0
    for signal in signals:
        price = int(_to_float(signal.get("current_price", signal.get("price"))))
        if price <= 0:
            continue
        top_features = {
            "themes": signal.get("themes", []),
            "narratives": signal.get("narratives", []),
            "breakdown": signal.get("breakdown", []),
            "price_source": "signal",
        }
        saved_id = save_scanned_candidate(
            symbol=signal.get("ticker", ""),
            name=signal.get("name", signal.get("ticker", "")),
            score=signal.get("score", 0),
            reasons=signal.get("reasons", []),
            price=price,
            env=trader.TRADING_ENV,
            indicators={},
            strategy={"id": STRATEGY_ID},
            ranker_model="rule_only",
            optimizer="narrative_momentum",
            scoring={
                "rule_score": signal.get("rule_score"),
                "ml_score": signal.get("ml_score"),
                "final_score": signal.get("final_score"),
                "ai_model_status": "not_used",
                "top_features": top_features,
            },
        )
        if saved_id:
            saved_count += 1
    return saved_count


def _create_approval_row(payload: dict[str, Any]) -> int:
    action = str(payload.get("action", "")).lower()
    if action not in {"buy", "sell"}:
        raise HTTPException(status_code=400, detail="action must be buy or sell")
    symbol = str(payload.get("symbol") or "").strip()
    if not symbol:
        raise HTTPException(status_code=400, detail="symbol is required")
    qty = int(_to_float(payload.get("qty")))
    if qty <= 0:
        raise HTTPException(status_code=400, detail="qty must be greater than 0")
    price = int(_to_float(payload.get("price")))
    now = trader.datetime.now(trader.KST).strftime("%Y-%m-%d %H:%M:%S")
    init_db()
    with trader.connect_db() as conn:
        cursor = conn.execute(
            """
            INSERT INTO approvals
            (
                created_at, updated_at, symbol, name, action, qty, price, reason, source,
                status, response_msg, strategy_id, strategy_version, profile_hash, source_candidate_id
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', '', ?, ?, ?, ?)
            """,
            (
                now,
                now,
                symbol,
                str(payload.get("name") or symbol),
                action,
                qty,
                price,
                str(payload.get("reason") or ""),
                str(payload.get("source") or "narrative_momentum"),
                str(payload.get("strategy_id") or STRATEGY_ID),
                None,
                None,
                None,
            ),
        )
        return int(cursor.lastrowid)


def _has_pending_buy(symbol: str) -> bool:
    init_db()
    try:
        with trader.connect_db() as conn:
            row = conn.execute(
                """
                SELECT id FROM approvals
                WHERE symbol = ? AND action = 'buy' AND status = 'pending'
                LIMIT 1
                """,
                (symbol,),
            ).fetchone()
            return row is not None
    except (sqlite3.Error, OSError, ValueError, TypeError) as exc:
        logger.warning(f"Failed to check pending narrative approval: {exc}")
        return False


def _to_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _display_path(path: Path) -> str:
    try:
        return str(path.relative_to(BASE_DIR))
    except ValueError:
        return str(path)
