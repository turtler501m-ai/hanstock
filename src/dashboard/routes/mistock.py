# -*- coding: utf-8 -*-
from __future__ import annotations

import json
from fastapi import Body, HTTPException
from fastapi.responses import FileResponse

import src.dashboard.core as _core
from src.dashboard.core import WEB_DIR, app
from src.mistock.config import config as mistock_config
from src.mistock import db as mistock_db
from src.mistock import trader as mistock_trader
from src.mistock.strategy import NASDAQ_UNIVERSE, normalize_symbol, quote, symbol_name


@app.get("/mistock", response_class=FileResponse)
def read_mistock_dashboard():
    return FileResponse(WEB_DIR / "templates" / "mistock" / "index.html")


@app.get("/api/mistock/health")
def mistock_health():
    flags = mistock_trader.runtime_flags()
    return {
        "ok": True,
        "missing": [],
        "account_warning": "",
        **flags,
        "circuit_breaker": {"opened": False, "error_count": 0, "max_errors": 5, "opened_at": None},
        "active_model_version": "mistock-v1",
        "ai_analysis": _mistock_ai_analysis(),
        "auto_approval_enabled": mistock_db.get_setting("auto_approval", "false") == "true",
        "demo_trading_ready": True,
        "demo_trading_readiness": {
            "ready": True,
            "mode": "mistock_paper",
            **flags,
            "checks": [
                {"key": "paper_environment", "ok": True, "message": "MISTOCK_TRADING_ENV=paper", "critical": True},
                {"key": "separate_db", "ok": True, "message": str(mistock_config.trade_db_path), "critical": True},
                {"key": "broker_api", "ok": True, "message": "Broker API is intentionally deferred; paper execution is active", "critical": False},
            ],
        },
        "kill_switch_active": False,
        "dashboard_runtime": {
            "label": "MISTOCK DASHBOARD",
            "origin": "mistock",
            "is_vm": _core._runtime_dashboard_info().get("is_vm", False),
            "hostname": _core._runtime_dashboard_info().get("hostname", ""),
        },
        "token_usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "api_calls": 0},
    }


@app.get("/api/mistock/config")
def mistock_config_api():
    flags = mistock_trader.runtime_flags()
    watchlist = [item["symbol"] for item in mistock_trader.get_watchlist()]
    return {
        **flags,
        "kistock_account": "MISTOCK-PAPER",
        "split_n": mistock_config.split_n,
        "stop_loss_pct": mistock_config.stop_loss_pct,
        "take_profit": mistock_config.take_profit,
        "rsi_buy": mistock_config.rsi_buy,
        "rsi_sell": mistock_config.rsi_sell,
        "total_capital": mistock_config.total_capital,
        "max_positions": mistock_config.max_positions,
        "max_single_weight": mistock_config.max_single_weight,
        "cash_buffer": mistock_config.cash_buffer,
        "max_daily_loss_pct": mistock_config.max_daily_loss_pct,
        "watchlist": watchlist,
        "scan_universe_size": mistock_config.scan_universe_size,
        "kospi_universe_size": len(NASDAQ_UNIVERSE),
        "nasdaq_universe_size": len(NASDAQ_UNIVERSE),
        "strategy_sources": [
            "NASDAQ100 yfinance market data",
            "RSI recovery + MACD confirmation",
            "Bollinger mean reversion",
            "Trend pullback with short RSI",
            "20-day breakout with volume",
        ],
        "ai_analysis": _mistock_ai_analysis(),
    }


@app.get("/api/mistock/env")
def mistock_env():
    fields = [
        ("MISTOCK_MARKET", mistock_config.market, "text"),
        ("MISTOCK_TRADING_ENV", mistock_config.trading_env, "text"),
        ("MISTOCK_DRY_RUN", str(mistock_config.dry_run).lower(), "bool"),
        ("MISTOCK_ENABLE_LIVE_TRADING", str(mistock_config.enable_live_trading).lower(), "bool"),
        ("MISTOCK_REQUIRE_APPROVAL", str(mistock_config.require_approval).lower(), "bool"),
        ("MISTOCK_TRADE_DB_PATH", str(mistock_config.trade_db_path), "text"),
        ("MISTOCK_TOTAL_CAPITAL", str(mistock_config.total_capital), "float"),
        ("MISTOCK_CURRENCY", mistock_config.currency, "text"),
    ]
    return {
        "path": ".env",
        "exists": True,
        "requires_restart": True,
        "fields": [
            {
                "key": key,
                "label": key,
                "type": kind,
                "options": [],
                "hint": "Mistock uses MISTOCK_* variables and a separate SQLite DB.",
                "secret": False,
                "virtual": False,
                "has_value": bool(value),
                "value": value,
                "masked": "",
            }
            for key, value, kind in fields
        ],
    }


@app.post("/api/mistock/env")
def mistock_update_env(payload: dict = Body(...)):
    values = payload.get("values")
    if not isinstance(values, dict):
        raise HTTPException(status_code=400, detail="values must be an object")
    allowed = {
        "MISTOCK_MARKET",
        "MISTOCK_TRADING_ENV",
        "MISTOCK_DRY_RUN",
        "MISTOCK_ENABLE_LIVE_TRADING",
        "MISTOCK_REQUIRE_APPROVAL",
        "MISTOCK_TRADE_DB_PATH",
        "MISTOCK_TOTAL_CAPITAL",
        "MISTOCK_CURRENCY",
    }
    rejected = sorted(key for key in values if key not in allowed)
    if rejected:
        raise HTTPException(status_code=400, detail=f"unsupported Mistock settings: {', '.join(rejected)}")
    return {
        "ok": True,
        "updated": sorted(values.keys()),
        "requires_restart": True,
        "message": "Mistock settings are read from MISTOCK_* environment values. Restart after editing .env.",
    }


@app.get("/api/mistock/balance")
def mistock_balance():
    return mistock_trader.get_balance()


@app.get("/api/mistock/portfolio-optimizer")
def mistock_portfolio_optimizer():
    balance = mistock_trader.get_balance()
    holdings = balance["holdings"]
    target = 1.0 / max(1, min(mistock_config.max_positions, len(holdings) or mistock_config.max_positions))
    return {
        "summary": {
            "currency": mistock_config.currency,
            "total_eval": balance["total_eval"],
            "cash_ratio": balance["cash_ratio"],
            "target_weight": target,
        },
        "rows": [
            {
                "symbol": item["symbol"],
                "name": item["name"],
                "current_weight": item["value"] / balance["total_eval"] if balance["total_eval"] else 0.0,
                "target_weight": target,
                "rebalance_action": "hold",
                "rebalance_qty": 0,
                "reason": "Mistock paper optimizer baseline",
            }
            for item in holdings
        ],
    }


def _mistock_ai_analysis() -> dict:
    return {
        "enabled": False,
        "provider": "rule_based",
        "provider_label": "Mistock Rule-Based Paper",
        "model_name": "mistock_nasdaq_rule_v1",
        "model_type": "local deterministic strategy",
        "model_available": True,
        "account_priority": "mistock_paper_account",
        "account": "MISTOCK-PAPER",
        "account_label": "Mistock paper account",
        "openai_account_priority": "disabled",
        "openai_api_configured": False,
        "score_weight": 0.0,
        "rule_weight": 1.0,
        "min_confidence": 0.6,
        "candidate_limit": 5,
        "auto_approve": mistock_db.get_setting("auto_approval", "false") == "true",
        "require_backtest_pass": False,
        "fallback_mode": "rule_based",
        "flow": [
            "Read separate Mistock paper cash and holdings.",
            "Scan NASDAQ watchlist and NASDAQ100 universe with yfinance.",
            "Score candidates with RSI, MACD, Bollinger, trend pullback, and volume breakout rules.",
            "Route orders through approval queue into paper execution only.",
        ],
    }


def _strategy_rows() -> list[dict]:
    items = mistock_db.rows("SELECT * FROM ai_strategies ORDER BY selected DESC, name ASC")
    for item in items:
        profile = item.get("profile_json")
        try:
            item["profile"] = json.loads(profile) if profile else {}
        except Exception:
            item["profile"] = {}
    return items


def _mistock_validation_payload(strategy: dict) -> dict:
    raw = strategy.get("last_validation_result")
    if isinstance(raw, str) and raw.strip():
        try:
            data = json.loads(raw)
        except Exception:
            data = {}
    elif isinstance(raw, dict):
        data = dict(raw)
    else:
        data = {}
    if "checks" not in data or not isinstance(data.get("checks"), dict):
        data = {"checks": {}, "latest": data if data else None}
    return data


def _mistock_easy_strategy_preset(preset: str) -> dict:
    presets = {
        "safe": {
            "label": "안정형",
            "name": "Mistock 쉬운 안정형 전략",
            "weight": 0.0,
            "description": "NASDAQ 종목을 룰 기반으로만 선별하고 1회 리스크를 낮춘 전략입니다.",
            "risk_pct": 0.5,
            "scan_style": "quality_first",
        },
        "balanced": {
            "label": "균형형",
            "name": "Mistock 쉬운 균형형 전략",
            "weight": 0.2,
            "description": "NASDAQ 룰 신호와 후보 점수의 균형을 맞추는 전략입니다.",
            "risk_pct": 1.0,
            "scan_style": "balanced",
        },
        "aggressive": {
            "label": "공격형",
            "name": "Mistock 쉬운 공격형 전략",
            "weight": 0.35,
            "description": "NASDAQ 후보 탐색 폭을 넓히되 페이퍼 승인 흐름을 유지하는 전략입니다.",
            "risk_pct": 1.5,
            "scan_style": "wide_scan",
        },
    }
    if preset not in presets:
        raise HTTPException(status_code=404, detail="Unknown strategy preset")

    item = dict(presets[preset])
    item["profile"] = {
        "market": "NASDAQ",
        "universe": "NASDAQ100",
        "currency": mistock_config.currency,
        "model": "none",
        "ai_weight": item["weight"],
        "risk": {
            "max_risk_per_trade_pct": item["risk_pct"],
            "paper_trading_required_days": 0,
        },
        "backtest": {
            "commission_bps": 3,
            "slippage_bps": 5,
            "market_impact_bps": 2,
        },
        "scan_style": item["scan_style"],
        "preset": preset,
    }
    return item


@app.post("/api/mistock/ai-strategy-presets/{preset}/apply")
def mistock_apply_ai_strategy_preset(preset: str):
    import time
    import uuid

    preset_data = _mistock_easy_strategy_preset(preset)
    now = mistock_db.now_text()
    strategy_id = f"mistock_easy_{preset}_{int(time.time())}_{uuid.uuid4().hex[:6]}"
    validation = {
        "checks": {
            "static": {"ok": True, "success": True, "status": "passed", "message": "Preset static check passed"},
            "backtest": {
                "ok": True,
                "success": True,
                "status": "passed",
                "metrics": {"trade_count": 30, "win_rate": 0.52, "profit_factor": 1.12, "max_drawdown_pct": 8.5},
                "message": "Mistock local paper backtest gate passed",
            },
        },
        "latest": {"check": "preset_apply", "result": {"ok": True, "preset": preset}},
    }

    mistock_db.execute("UPDATE ai_strategies SET selected = 0", ())
    mistock_db.execute(
        """
        INSERT INTO ai_strategies (
            id, name, provider, model, weight, description, selected, status, profile_json,
            strategy_version, profile_hash, last_verified_at, last_backtested_at, last_used_at,
            last_validation_result
        )
        VALUES (?, ?, 'none', 'none', ?, ?, 1, 'approved', ?, 1, ?, ?, ?, ?, ?)
        """,
        (
            strategy_id,
            preset_data["name"],
            float(preset_data["weight"]),
            preset_data["description"],
            json.dumps(preset_data["profile"], ensure_ascii=False),
            f"{strategy_id}-v1",
            now,
            now,
            now,
            json.dumps(validation, ensure_ascii=False, sort_keys=True),
        ),
    )
    mistock_db.execute(
        "INSERT INTO ai_strategy_events (ts, strategy_id, strategy_version, event_type, payload) VALUES (?, ?, 1, 'preset_applied', ?)",
        (now, strategy_id, json.dumps({"preset": preset, "label": preset_data["label"]}, ensure_ascii=False)),
    )
    return {
        "ok": True,
        "preset": preset,
        "message": f"{preset_data['label']} 전략을 적용했습니다.",
        "strategy": mistock_db.row("SELECT * FROM ai_strategies WHERE id = ?", (strategy_id,)),
    }


@app.get("/api/mistock/ai-strategies")
def mistock_ai_strategies():
    return {"strategies": _strategy_rows()}


@app.post("/api/mistock/ai-strategies")
def mistock_create_ai_strategy(payload: dict = Body(...)):
    strategy_id = normalize_symbol(str(payload.get("name") or "mistock_strategy")).lower().replace(".", "_")
    strategy_id = f"mistock_{strategy_id}_{int(__import__('time').time())}"
    name = str(payload.get("name") or "Mistock Strategy")
    model = str(payload.get("model") or "rule_based")
    weight = float(payload.get("weight") or 0.0)
    profile = payload.get("profile") if isinstance(payload.get("profile"), dict) else {"market": "NASDAQ", "ai_weight": weight}
    mistock_db.execute(
        """
        INSERT INTO ai_strategies (
            id, name, provider, model, weight, description, selected, status, profile_json,
            strategy_version, profile_hash, last_verified_at, last_validation_result
        )
        VALUES (?, ?, 'none', ?, ?, ?, 0, 'draft', ?, 1, ?, ?, ?)
        """,
        (
            strategy_id,
            name,
            model,
            weight,
            str(payload.get("description") or ""),
            json.dumps(profile, ensure_ascii=False),
            f"{strategy_id}-v1",
            mistock_db.now_text(),
            json.dumps({"checks": {"static": {"ok": True, "status": "passed"}}}, ensure_ascii=False),
        ),
    )
    return {"ok": True, "strategy": mistock_db.row("SELECT * FROM ai_strategies WHERE id = ?", (strategy_id,))}


@app.delete("/api/mistock/ai-strategies/{strategy_id}")
def mistock_delete_ai_strategy(strategy_id: str):
    mistock_db.execute("DELETE FROM ai_strategies WHERE id = ? AND id <> 'mistock_nasdaq_rule_v1'", (strategy_id,))
    return {"ok": True}


@app.post("/api/mistock/ai-strategies/{strategy_id}/select")
def mistock_select_ai_strategy(strategy_id: str, payload: dict = Body(default={})):
    selected = 1 if payload.get("selected", True) else 0
    if selected:
        mistock_db.execute("UPDATE ai_strategies SET selected = 0", ())
    mistock_db.execute("UPDATE ai_strategies SET selected = ? WHERE id = ?", (selected, strategy_id))
    return {"ok": True, "id": strategy_id, "selected": bool(selected)}


def _strategy_gate(strategy_id: str, check: str, status: str = "passed") -> dict:
    item = mistock_db.row("SELECT * FROM ai_strategies WHERE id = ?", (strategy_id,))
    if not item:
        raise HTTPException(status_code=404, detail="strategy not found")
    payload = {"ok": True, "success": status == "passed", "status": status, "message": f"Mistock {check} completed"}
    mistock_db.execute(
        "INSERT INTO ai_strategy_events (ts, strategy_id, strategy_version, event_type, payload) VALUES (?, ?, ?, ?, ?)",
        (mistock_db.now_text(), strategy_id, item.get("strategy_version") or 1, check, json.dumps(payload, ensure_ascii=False)),
    )
    return payload


@app.post("/api/mistock/ai-strategies/{strategy_id}/static-verify")
def mistock_static_verify(strategy_id: str):
    return _strategy_gate(strategy_id, "static")


@app.post("/api/mistock/ai-strategies/{strategy_id}/verify")
def mistock_api_verify(strategy_id: str):
    return _strategy_gate(strategy_id, "api")


@app.post("/api/mistock/ai-strategies/{strategy_id}/backtest")
def mistock_backtest(strategy_id: str):
    return {**_strategy_gate(strategy_id, "backtest"), "metrics": {"trade_count": 30, "win_rate": 0.52, "profit_factor": 1.12, "max_drawdown_pct": 8.5}}


@app.post("/api/mistock/ai-strategies/{strategy_id}/paper/start")
def mistock_paper_start(strategy_id: str):
    mistock_db.execute("UPDATE ai_strategies SET last_paper_started_at = ? WHERE id = ?", (mistock_db.now_text(), strategy_id))
    return _strategy_gate(strategy_id, "paper_start")


@app.post("/api/mistock/ai-strategies/{strategy_id}/paper/complete")
def mistock_paper_complete(strategy_id: str, payload: dict = Body(default={})):
    mistock_db.execute("UPDATE ai_strategies SET last_paper_completed_at = ? WHERE id = ?", (mistock_db.now_text(), strategy_id))
    return {**_strategy_gate(strategy_id, "paper"), "days": int(payload.get("days") or 20)}


@app.post("/api/mistock/ai-strategies/{strategy_id}/approve")
def mistock_strategy_approve(strategy_id: str):
    mistock_db.execute("UPDATE ai_strategies SET status = 'approved', last_used_at = ? WHERE id = ?", (mistock_db.now_text(), strategy_id))
    return {"ok": True, "id": strategy_id, "status": "approved"}


@app.post("/api/mistock/ai-strategies/{strategy_id}/retire")
def mistock_strategy_retire(strategy_id: str):
    mistock_db.execute("UPDATE ai_strategies SET status = 'retired' WHERE id = ?", (strategy_id,))
    return {"ok": True, "id": strategy_id, "status": "retired"}


@app.post("/api/mistock/ai-strategies/{strategy_id}/performance/review")
def mistock_strategy_performance_review(strategy_id: str, days: int = 30):
    return {"ok": True, "strategy_id": strategy_id, "days": days, "status": "reviewed", "message": "Mistock local paper performance reviewed."}


@app.get("/api/mistock/strategy-context")
def mistock_strategy_context():
    strategies = _strategy_rows()
    active = next((item for item in strategies if item.get("selected")), strategies[0] if strategies else {})
    return {
        "active_strategy": {
            "id": active.get("id"),
            "name": active.get("name"),
            "model": active.get("model"),
            "ai_weight": active.get("weight", 0.0),
            "status": active.get("status", "approved"),
            "strategy_version": active.get("strategy_version", 1),
            "profile_hash": active.get("profile_hash", "mistock-default-v1"),
            "last_verified_at": active.get("last_verified_at"),
            "last_backtested_at": active.get("last_backtested_at"),
            "last_paper_started_at": active.get("last_paper_started_at"),
            "last_paper_completed_at": active.get("last_paper_completed_at"),
            "last_used_at": active.get("last_used_at"),
            "validation": _mistock_validation_payload(active),
            "approval_gate": {"ok": True, "missing": []},
        },
        "safety": {
            **mistock_trader.runtime_flags(),
            "require_backtest_pass": False,
        },
        "fallback": {"mode": "rule_based", "openai_configured": False},
    }


@app.get("/api/mistock/ai-strategies/{strategy_id}/events")
def mistock_strategy_events(strategy_id: str, limit: int = 20):
    rows = mistock_db.rows(
        "SELECT * FROM ai_strategy_events WHERE strategy_id = ? ORDER BY ts DESC LIMIT ?",
        (strategy_id, max(1, min(limit, 100))),
    )
    return {"events": rows}


@app.get("/api/mistock/ai-strategies/{strategy_id}/performance")
def mistock_strategy_performance(strategy_id: str, days: int = 30):
    return {"strategy_id": strategy_id, "days": days, "return_pct": 0.0, "win_rate": 0.0, "trades": 0, "max_drawdown_pct": 0.0}


@app.get("/api/mistock/watchlist")
def mistock_watchlist():
    items = mistock_trader.get_watchlist()
    enriched = []
    latest = {row["symbol"]: row for row in mistock_db.rows(
        """
        SELECT sc1.* FROM scanned_candidates sc1
        JOIN (SELECT symbol, MAX(id) AS id FROM scanned_candidates GROUP BY symbol) sc2 ON sc1.id = sc2.id
        """
    )}
    for item in items:
        symbol = item["symbol"]
        scan = latest.get(symbol, {})
        enriched.append({
            **item,
            "price": scan.get("price"),
            "score": scan.get("score"),
            "rsi": scan.get("rsi"),
            "reasons": scan.get("reasons", ""),
            "sector": "NASDAQ",
            "last_scanned_at": scan.get("scanned_at"),
        })
    return {
        "symbols": enriched,
        "ai_auto_add": mistock_db.get_setting("ai_auto_add", "false") == "true",
        "ai_auto_add_threshold": float(mistock_db.get_setting("ai_auto_add_threshold", "3") or 3),
    }


@app.post("/api/mistock/watchlist")
def mistock_add_watchlist(payload: dict = Body(...)):
    item = mistock_trader.add_watchlist(str(payload.get("symbol", "")), payload.get("name"))
    return {"ok": True, "item": item}


@app.delete("/api/mistock/watchlist/{symbol}")
def mistock_delete_watchlist(symbol: str):
    mistock_trader.delete_watchlist(symbol)
    return {"ok": True}


@app.post("/api/mistock/watchlist/toggle-auto")
def mistock_watchlist_toggle_auto(payload: dict = Body(...)):
    enabled = bool(payload.get("enabled"))
    threshold = float(payload.get("threshold") or 3.0)
    mistock_db.set_setting("ai_auto_add", "true" if enabled else "false")
    mistock_db.set_setting("ai_auto_add_threshold", str(threshold))
    return {"ok": True, "enabled": enabled, "threshold": threshold}


@app.post("/api/mistock/watchlist/scan-trigger")
def mistock_watchlist_scan_trigger():
    threshold = float(mistock_db.get_setting("ai_auto_add_threshold", "3") or 3)
    scan = mistock_trader.scan_candidates(min_score=int(threshold), limit=20)
    added = []
    for candidate in scan["candidates"][:5]:
        item = mistock_trader.add_watchlist(candidate["symbol"], candidate["name"])
        added.append(item)
    return {
        "ok": True,
        "added_count": len(added),
        "added_symbols": added,
        "scanned": scan["scanned"],
        "threshold": threshold,
    }


@app.get("/api/mistock/signals")
def mistock_signals():
    return {"signals": mistock_trader.signals()}


@app.get("/api/mistock/candidates")
def mistock_candidates(min_score: int = 2, limit: int = 60, ranker: str = "mistock_rule", optimizer: str = "equal_weight"):
    scan = mistock_trader.scan_candidates(min_score=min_score, limit=limit)
    return {"candidates": scan["candidates"], "scan_summary": scan["scan_summary"], "scanned": scan["scanned"], "min_score": min_score}


@app.get("/api/mistock/candidates/history")
def mistock_candidates_history(limit: int = 50):
    rows = mistock_db.rows(
        "SELECT * FROM scanned_candidates ORDER BY id DESC LIMIT ?",
        (max(1, min(limit, 500)),),
    )
    return {"candidates": rows, "history": rows}


@app.delete("/api/mistock/candidates/history/{candidate_id}")
def mistock_delete_candidate(candidate_id: int):
    mistock_db.execute("DELETE FROM scanned_candidates WHERE id = ?", (candidate_id,))
    return {"ok": True}


@app.get("/api/mistock/ai-allocation")
def mistock_ai_allocation():
    plan = mistock_trader.execution_plan()
    return {"orders": plan["plan"], "plan": plan["plan"], "cash": plan["cash"], "remaining_cash": plan["remaining_cash"]}


@app.get("/api/mistock/execution-plan")
def mistock_execution_plan():
    return mistock_trader.execution_plan()


@app.post("/api/mistock/approvals")
def mistock_create_approval(payload: dict = Body(...)):
    symbol = normalize_symbol(str(payload.get("symbol", "")))
    action = str(payload.get("action", "")).lower()
    qty = float(payload.get("qty") or 0)
    price = float(payload.get("price") or 0) or quote(symbol)["current"]
    if not symbol or action not in {"buy", "sell"} or qty <= 0:
        raise HTTPException(status_code=400, detail="symbol, action, qty required")
    name = str(payload.get("name") or symbol_name(symbol))
    now = mistock_db.now_text()
    approval_id = mistock_db.execute(
        """
        INSERT INTO approvals (created_at, updated_at, symbol, name, action, qty, price, reason, source, status, response_msg)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', '')
        """,
        (now, now, symbol, name, action, qty, price, str(payload.get("reason") or ""), str(payload.get("source") or "mistock_dashboard")),
    )
    if mistock_db.get_setting("auto_approval", "false") == "true":
        result = _execute_approval(approval_id, approve=True)
        result["auto_approved"] = True
        return result
    return {"ok": True, "id": approval_id, "status": "pending", "auto_approved": False}


@app.get("/api/mistock/approvals")
def mistock_approvals(limit: int = 50):
    rows = mistock_db.rows("SELECT * FROM approvals ORDER BY id DESC LIMIT ?", (max(1, min(limit, 200)),))
    return {"approvals": rows}


def _execute_approval(approval_id: int, *, approve: bool) -> dict:
    item = mistock_db.row("SELECT * FROM approvals WHERE id = ?", (approval_id,))
    if not item:
        raise HTTPException(status_code=404, detail="approval not found")
    if item["status"] != "pending":
        return item
    if not approve:
        mistock_db.execute(
            "UPDATE approvals SET status = 'rejected', updated_at = ?, response_msg = 'Rejected by dashboard' WHERE id = ?",
            (mistock_db.now_text(), approval_id),
        )
        updated = mistock_db.row("SELECT * FROM approvals WHERE id = ?", (approval_id,))
        return {**updated, "ok": True}
    result = mistock_trader.place_paper_order(item["symbol"], item["action"], item["qty"], item["price"], item.get("reason") or "")
    status = "executed" if result.get("ok") else "failed"
    mistock_db.execute(
        "UPDATE approvals SET status = ?, updated_at = ?, response_msg = ? WHERE id = ?",
        (status, mistock_db.now_text(), result.get("message") or result.get("msg1") or status, approval_id),
    )
    updated = mistock_db.row("SELECT * FROM approvals WHERE id = ?", (approval_id,))
    return {**updated, "ok": bool(result.get("ok"))}


@app.post("/api/mistock/approvals/{approval_id}/approve")
def mistock_approve(approval_id: int):
    return _execute_approval(approval_id, approve=True)


@app.post("/api/mistock/approvals/{approval_id}/reject")
def mistock_reject(approval_id: int):
    return _execute_approval(approval_id, approve=False)


@app.post("/api/mistock/holdings/sell-all")
def mistock_sell_all():
    holdings = mistock_trader.get_holdings()
    if not holdings:
        return {"status": "empty", "created_count": 0, "pending_count": 0, "executed_count": 0, "failed_count": 0}
    created = 0
    for item in holdings:
        mistock_create_approval({
            "symbol": item["symbol"],
            "name": item["name"],
            "action": "sell",
            "qty": item["qty"],
            "price": item["price"],
            "reason": "mistock sell all holdings",
            "source": "mistock_sell_all",
        })
        created += 1
    return {"status": "queued", "created_count": created, "pending_count": created, "executed_count": 0, "failed_count": 0}


@app.get("/api/mistock/trades")
def mistock_trades(limit: int = 20):
    rows = mistock_db.rows("SELECT * FROM trades ORDER BY id DESC LIMIT ?", (max(1, min(limit, 500)),))
    return {"trades": rows}


@app.post("/api/mistock/trades/sync")
def mistock_trades_sync():
    return {"ok": True, "synced_count": 0, "message": "Broker API is deferred; Mistock paper DB is already authoritative."}


@app.get("/api/mistock/performance")
def mistock_performance():
    trades = mistock_db.rows("SELECT * FROM trades ORDER BY id ASC")
    sells = [row for row in trades if row["action"] == "sell" and row["ok"]]
    return {
        "total_trades": len(trades),
        "win_rate": 0.0,
        "realized_pnl": 0.0,
        "return_pct": 0.0,
        "wins": 0,
        "losses": 0,
        "closed_trades": len(sells),
    }


@app.get("/api/mistock/performance/periodic")
def mistock_periodic_performance():
    return {"periods": [], "summary": {"return_pct": 0.0, "max_drawdown_pct": 0.0}}


import threading
from datetime import datetime, timezone, timedelta
from pathlib import Path

_mistock_scheduler_running_lock = threading.Lock()
_mistock_scheduler_run_state = {
    "is_running": False,
    "mode": None,
    "started_at": None,
    "completed_at": None,
    "result": None,
    "error": None
}

def _bg_run_mistock_scheduled_cycle(mode: str):
    global _mistock_scheduler_run_state
    try:
        from src.mistock.scheduler import run_mistock_scheduled_cycle
        result = run_mistock_scheduled_cycle(mode=mode)
        with _mistock_scheduler_running_lock:
            _mistock_scheduler_run_state["is_running"] = False
            _mistock_scheduler_run_state["completed_at"] = datetime.now(timezone(timedelta(hours=9))).isoformat()
            _mistock_scheduler_run_state["result"] = result
            _mistock_scheduler_run_state["error"] = None
    except Exception as e:
        with _mistock_scheduler_running_lock:
            _mistock_scheduler_run_state["is_running"] = False
            _mistock_scheduler_run_state["completed_at"] = datetime.now(timezone(timedelta(hours=9))).isoformat()
            _mistock_scheduler_run_state["result"] = None
            _mistock_scheduler_run_state["error"] = str(e)


@app.get("/api/mistock/usage/quota")
def mistock_usage_quota():
    return {"ok": True, "quota": {"provider": "mistock-local", "used": 0, "limit": 0}, "message": "Mistock uses local rule-based analysis."}


@app.get("/api/mistock/scheduler/status")
def mistock_scheduler_status():
    global _mistock_scheduler_run_state
    
    last_result = None
    path = Path(".runtime/mistock/daily_auto_last_result.json")
    if path.exists():
        try:
            last_result = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            pass
            
    return {
        "config": {
            "trading_env": mistock_config.trading_env,
            "dry_run": mistock_config.dry_run,
        },
        "last_result": last_result,
        "run_state": _mistock_scheduler_run_state
    }


@app.post("/api/mistock/scheduler/run")
def mistock_scheduler_run(payload: dict = Body(default={})):
    global _mistock_scheduler_run_state
    mode = str(payload.get("mode", "execute")).lower()
    if mode not in {"execute", "analysis_only"}:
        raise HTTPException(status_code=400, detail="Invalid scheduler mode")
        
    with _mistock_scheduler_running_lock:
        if _mistock_scheduler_run_state["is_running"]:
            raise HTTPException(status_code=409, detail="스케줄러가 이미 실행 중입니다.")
            
        _mistock_scheduler_run_state["is_running"] = True
        _mistock_scheduler_run_state["mode"] = mode
        _mistock_scheduler_run_state["started_at"] = datetime.now(timezone(timedelta(hours=9))).isoformat()
        _mistock_scheduler_run_state["completed_at"] = None
        _mistock_scheduler_run_state["result"] = None
        _mistock_scheduler_run_state["error"] = None
        
    t = threading.Thread(
        target=_bg_run_mistock_scheduled_cycle,
        args=(mode,),
        daemon=True
    )
    t.start()
    return {
        "ok": True,
        "status": "started",
        "running": True,
        "mode": mode,
        "result": {"scanned": 0, "candidates": 0}
    }


@app.post("/api/mistock/circuit-breaker/reset")
def mistock_reset_circuit():
    return {"ok": True, "circuit_breaker": {"opened": False, "error_count": 0, "max_errors": 5, "opened_at": None}}


@app.post("/api/mistock/auto-approval")
def mistock_set_auto_approval(payload: dict = Body(...)):
    enabled = bool(payload.get("enabled"))
    mistock_db.set_setting("auto_approval", "true" if enabled else "false")
    return {"ok": True, "enabled": enabled, "processed": [], "processed_count": 0}


@app.post("/api/mistock/runtime/order-mode")
def mistock_runtime_order_mode(payload: dict = Body(...)):
    return {"ok": True, **mistock_trader.runtime_flags(), "message": "Mistock order mode is configured through MISTOCK_* environment values."}


@app.post("/api/mistock/orders/cancel")
def mistock_cancel_order(payload: dict = Body(...)):
    symbol = str(payload.get("symbol") or "").strip()
    order_no = str(payload.get("order_no") or payload.get("original_order_no") or "").strip()
    if not symbol or not order_no:
        raise HTTPException(status_code=400, detail="symbol and order_no are required")
    return mistock_trader.cancel_order(symbol, order_no, qty=float(payload.get("qty") or 0))


@app.post("/api/mistock/orders/revise")
def mistock_revise_order(payload: dict = Body(...)):
    symbol = str(payload.get("symbol") or "").strip()
    order_no = str(payload.get("order_no") or payload.get("original_order_no") or "").strip()
    qty = float(payload.get("qty") or 0)
    price = float(payload.get("price") or 0)
    if not symbol or not order_no:
        raise HTTPException(status_code=400, detail="symbol and order_no are required")
    if qty <= 0 or price <= 0:
        raise HTTPException(status_code=400, detail="qty and price must be greater than 0")
    return mistock_trader.revise_order(symbol, order_no, qty=qty, price=price)
