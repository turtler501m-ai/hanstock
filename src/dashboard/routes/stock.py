# -*- coding: utf-8 -*-
from fastapi import Body, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
import src.dashboard.core as _core
from src.dashboard.core import *
from src.utils.logger import logger
globals().update({k: v for k, v in _core.__dict__.items() if not k.startswith('__')})

class NewStrategyPayload(BaseModel):
    name: str = Field(..., min_length=1)
    model: str = "none"
    weight: float = 0.0
    description: str = ""
    profile: dict | None = None
    status: str | None = None


class UpdateStrategyPayload(BaseModel):
    name: str | None = None
    model: str | None = None
    weight: float | None = None
    description: str | None = None
    profile: dict | None = None
    status: str | None = None


class SelectStrategyPayload(BaseModel):
    selected: bool = True


class PaperCompletePayload(BaseModel):
    days: int = 20
    observations: int = 20
    return_pct: float = 0.0
    max_drawdown_pct: float = 0.0
    pass_result: bool | None = None
    notes: str | None = None


def _now_kst_text() -> str:
    return trader.datetime.now(trader.KST).strftime("%Y-%m-%d %H:%M:%S")


def _validation_payload(strategy: dict) -> dict:
    import json

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


def _store_validation_check(strategy: dict, check_name: str, result: dict) -> None:
    import json

    data = _validation_payload(strategy)
    data["checks"][check_name] = result
    data["latest"] = {"check": check_name, "result": result}
    strategy["last_validation_result"] = json.dumps(data, ensure_ascii=False, sort_keys=True)


def _check_passed(strategy: dict, check_name: str) -> bool:
    result = _validation_payload(strategy).get("checks", {}).get(check_name, {})
    return bool(result.get("success") or result.get("ok") is True and result.get("status") == "passed")


def _approval_gate(strategy: dict) -> dict:
    profile = strategy.get("profile") or {}
    risk = profile.get("risk") if isinstance(profile.get("risk"), dict) else {}
    require_paper = int(risk.get("paper_trading_required_days") or 0) > 0
    require_backtest = bool(getattr(trader.config, "ai_require_backtest_pass", True))
    missing = []
    if not _check_passed(strategy, "static"):
        missing.append("static verification")
    if strategy.get("provider") != "none" and not _check_passed(strategy, "api"):
        missing.append("api verification")
    if require_backtest and not _check_passed(strategy, "backtest"):
        missing.append("backtest")
    if require_paper and not _check_passed(strategy, "paper"):
        missing.append("paper trading")
    return {"ok": not missing, "missing": missing}


def _build_strategy_backtest(strategy: dict) -> dict:
    from src.strategy.backtest import run_historical_backtest
    profile = strategy.get("profile") or {}
    return run_historical_backtest(profile)


def _paper_result_from_payload(payload: PaperCompletePayload, strategy: dict) -> dict:
    profile = strategy.get("profile") or {}
    risk = profile.get("risk") if isinstance(profile.get("risk"), dict) else {}
    required_days = int(risk.get("paper_trading_required_days") or 20)
    passed = payload.pass_result
    if passed is None:
        passed = (
            payload.days >= required_days
            and payload.observations >= max(5, required_days // 2)
            and payload.max_drawdown_pct <= 10.0
        )
    return {
        "ok": True,
        "success": bool(passed),
        "status": "passed" if passed else "failed",
        "days": int(payload.days),
        "required_days": required_days,
        "observations": int(payload.observations),
        "return_pct": float(payload.return_pct),
        "max_drawdown_pct": float(payload.max_drawdown_pct),
        "notes": payload.notes or "",
        "message": "Paper trading gate completed",
    }


@app.get("/api/ai-strategies")
def get_ai_strategies():
    from src.db.repository import load_ai_strategies
    return {"strategies": load_ai_strategies()}


@app.get("/api/strategy-context")
def get_strategy_context():
    from src.db.repository import load_ai_strategies

    strategies = load_ai_strategies()
    active = next((strategy for strategy in strategies if strategy.get("selected")), None)
    if active is None and strategies:
        active = strategies[0]
    profile = active.get("profile") if active else {}
    return {
        "active_strategy": {
            "id": active.get("id") if active else None,
            "name": active.get("name") if active else None,
            "model": (profile or {}).get("model") or (active.get("model") if active else None),
            "ai_weight": (profile or {}).get("ai_weight") if active else 0.0,
            "status": active.get("status") if active else None,
            "strategy_version": active.get("strategy_version") if active else None,
            "profile_hash": active.get("profile_hash") if active else None,
            "last_verified_at": active.get("last_verified_at") if active else None,
            "last_backtested_at": active.get("last_backtested_at") if active else None,
            "last_paper_started_at": active.get("last_paper_started_at") if active else None,
            "last_paper_completed_at": active.get("last_paper_completed_at") if active else None,
            "last_used_at": active.get("last_used_at") if active else None,
            "validation": _validation_payload(active) if active else {"checks": {}},
            "approval_gate": _approval_gate(active) if active else {"ok": False, "missing": ["active strategy"]},
        },
        "safety": {
            "trading_env": trader.TRADING_ENV,
            "dry_run": bool(trader.DRY_RUN),
            "enable_live_trading": bool(trader.ENABLE_LIVE_TRADING),
            "require_approval": bool(trader.REQUIRE_APPROVAL),
            "require_backtest_pass": bool(getattr(trader.config, "ai_require_backtest_pass", True)),
        },
        "fallback": {
            "mode": "rule_based" if not bool(getattr(trader.config, "ai_strategy_enabled", False)) else "",
            "openai_configured": bool(str(getattr(trader.config, "openai_api_key", "") or "").strip()),
        },
    }




@app.post("/api/ai-strategies")
def create_ai_strategy(payload: NewStrategyPayload):
    from src.db.repository import load_ai_strategies, normalize_ai_strategy, record_ai_strategy_event, save_ai_strategies
    import time
    import uuid

    strategies = load_ai_strategies()
    new_id = f"strategy_{int(time.time())}_{uuid.uuid4().hex[:6]}"
    new_strat = normalize_ai_strategy({
        "id": new_id,
        "name": payload.name,
        "provider": "openai" if payload.model != "none" else "none",
        "model": payload.model,
        "weight": payload.weight,
        "description": payload.description,
        "selected": False,
        "status": payload.status or "draft",
        "profile": payload.profile,
        "strategy_version": 1,
    })
    strategies.append(new_strat)
    save_ai_strategies(strategies)
    record_ai_strategy_event(new_id, "created", {"name": payload.name, "model": payload.model}, 1)
    return {"ok": True, "strategy": new_strat}


@app.patch("/api/ai-strategies/{id}")
def update_ai_strategy(id: str, payload: UpdateStrategyPayload):
    from src.db.repository import load_ai_strategies, normalize_ai_strategy, record_ai_strategy_event, save_ai_strategies

    strategies = load_ai_strategies()
    found = None
    for idx, strategy in enumerate(strategies):
        if strategy["id"] != id:
            continue
        updated = dict(strategy)
        changes = payload.model_dump(exclude_unset=True)
        if "profile" in changes and changes["profile"] is not None:
            updated["profile"] = changes.pop("profile")
        updated.update({key: value for key, value in changes.items() if value is not None})
        updated["strategy_version"] = int(updated.get("strategy_version") or 1) + 1
        found = normalize_ai_strategy(updated)
        strategies[idx] = found
        break

    if not found:
        raise HTTPException(status_code=404, detail="Strategy not found")

    save_ai_strategies(strategies)
    record_ai_strategy_event(id, "updated", payload.model_dump(exclude_unset=True), found.get("strategy_version"))
    return {"ok": True, "strategy": found}


@app.delete("/api/ai-strategies/{id}")
def delete_ai_strategy(id: str):
    from src.db.repository import load_ai_strategies, record_ai_strategy_event, save_ai_strategies

    strategies = load_ai_strategies()
    target = next((strategy for strategy in strategies if strategy["id"] == id), None)
    if not target:
        raise HTTPException(status_code=404, detail="Strategy not found")
    if id in {"gpt_5_mini_default", "rule_only_default"}:
        raise HTTPException(status_code=409, detail="Built-in strategy cannot be deleted")

    save_ai_strategies([strategy for strategy in strategies if strategy["id"] != id])
    record_ai_strategy_event(id, "deleted", {"name": target.get("name")}, target.get("strategy_version"))
    return {"ok": True}




@app.post("/api/ai-strategies/{id}/select")
def select_ai_strategy(id: str, payload: SelectStrategyPayload):
    from src.db.repository import load_ai_strategies, record_ai_strategy_event, save_ai_strategies

    strategies = load_ai_strategies()
    found = None
    for strategy in strategies:
        if strategy["id"] == id:
            strategy["selected"] = payload.selected
            found = strategy
        elif payload.selected:
            strategy["selected"] = False

    if not found:
        raise HTTPException(status_code=404, detail="Strategy not found")

    save_ai_strategies(strategies)
    record_ai_strategy_event(id, "selected", {"selected": payload.selected}, found.get("strategy_version"))
    return {"ok": True}




def _static_validate_strategy(strategy: dict) -> dict:
    warnings = []
    errors = []
    profile = strategy.get("profile") or {}
    weight = float(profile.get("ai_weight", strategy.get("weight", 0.0)) or 0.0)
    if weight > 0.6:
        warnings.append("AI weight is high; consider <= 0.6 before live use")
    if not str(strategy.get("description") or "").strip():
        warnings.append("Description is empty; rationale will be less auditable")
    risk = profile.get("risk") if isinstance(profile.get("risk"), dict) else {}
    if not risk.get("max_risk_per_trade_pct"):
        warnings.append("Risk profile does not define max_risk_per_trade_pct")
    if profile.get("allow_candidate_promotion") and strategy.get("status") != "approved":
        warnings.append("Candidate promotion should stay disabled until approval")
    if strategy.get("provider") == "openai" and strategy.get("model") == "none":
        errors.append("OpenAI provider requires a model")
    return {
        "ok": not errors,
        "errors": errors,
        "warnings": warnings,
        "status": "passed" if not errors else "failed",
    }


def _easy_strategy_preset(preset: str) -> dict:
    presets = {
        "safe": {
            "label": "안정형",
            "name": "쉬운 안정형 전략",
            "weight": 0.0,
            "description": "AI 호출 없이 룰 기반 신호만 사용하고 1회 리스크를 낮춘 기본 전략입니다.",
            "risk_pct": 0.5,
            "allow_candidate_promotion": False,
        },
        "balanced": {
            "label": "균형형",
            "name": "쉬운 균형형 전략",
            "weight": 0.2,
            "description": "룰 기반 신호를 중심으로 후보 점수와 리스크 균형을 맞추는 전략입니다.",
            "risk_pct": 1.0,
            "allow_candidate_promotion": False,
        },
        "aggressive": {
            "label": "공격형",
            "name": "쉬운 공격형 전략",
            "weight": 0.35,
            "description": "더 많은 후보 탐색을 허용하되 승인 대기 흐름을 유지하는 전략입니다.",
            "risk_pct": 1.5,
            "allow_candidate_promotion": True,
        },
    }
    if preset not in presets:
        raise HTTPException(status_code=404, detail="Unknown strategy preset")

    item = dict(presets[preset])
    weight = float(item["weight"])
    item["profile"] = {
        "model": "none",
        "ai_weight": weight,
        "risk": {
            "max_risk_per_trade_pct": item["risk_pct"],
            "paper_trading_required_days": 0,
        },
        "backtest": {
            "commission_bps": 3,
            "slippage_bps": 5,
            "market_impact_bps": 2,
        },
        "allow_candidate_promotion": item["allow_candidate_promotion"],
        "preset": preset,
    }
    return item


@app.post("/api/ai-strategy-presets/{preset}/apply")
def apply_ai_strategy_preset(preset: str):
    from src.db.repository import load_ai_strategies, normalize_ai_strategy, record_ai_strategy_event, save_ai_strategies
    import json
    import time
    import uuid

    preset_data = _easy_strategy_preset(preset)
    now = _now_kst_text()
    strategy_id = f"easy_{preset}_{int(time.time())}_{uuid.uuid4().hex[:6]}"
    strategy = normalize_ai_strategy({
        "id": strategy_id,
        "name": preset_data["name"],
        "provider": "none",
        "model": "none",
        "weight": preset_data["weight"],
        "description": preset_data["description"],
        "selected": True,
        "status": "approved",
        "profile": preset_data["profile"],
        "strategy_version": 1,
        "last_verified_at": now,
        "last_backtested_at": now,
        "last_used_at": now,
    })
    static_result = _static_validate_strategy(strategy)
    static_result["success"] = bool(static_result.get("ok"))
    backtest_result = _build_strategy_backtest(strategy)
    strategy["last_validation_result"] = json.dumps(
        {
            "checks": {
                "static": static_result,
                "backtest": backtest_result,
            },
            "latest": {"check": "preset_apply", "result": {"ok": True, "preset": preset}},
        },
        ensure_ascii=False,
        sort_keys=True,
    )

    strategies = load_ai_strategies()
    for item in strategies:
        if item.get("name") == preset_data["name"]:
            item["status"] = "retired"
        item["selected"] = False
    strategies.append(strategy)
    save_ai_strategies(strategies)
    record_ai_strategy_event(
        strategy_id,
        "preset_applied",
        {"preset": preset, "label": preset_data["label"], "static": static_result, "backtest": backtest_result},
        1,
    )
    return {"ok": True, "preset": preset, "message": f"{preset_data['label']} 전략을 적용했습니다.", "strategy": strategy}


@app.post("/api/ai-strategies/{id}/static-verify")
def static_verify_ai_strategy(id: str):
    from src.db.repository import load_ai_strategies, record_ai_strategy_event, save_ai_strategies

    strategies = load_ai_strategies()
    strategy = next((item for item in strategies if item["id"] == id), None)
    if not strategy:
        raise HTTPException(status_code=404, detail="Strategy not found")

    result = _static_validate_strategy(strategy)
    result["success"] = bool(result.get("ok"))
    now = _now_kst_text()
    for item in strategies:
        if item["id"] == id:
            item["last_verified_at"] = now
            _store_validation_check(item, "static", result)
            if result["ok"] and item.get("status") == "draft":
                item["status"] = "verified"
            strategy = item
            break
    save_ai_strategies(strategies)
    record_ai_strategy_event(id, "static_verified", result, strategy.get("strategy_version"))
    return {"ok": True, "result": result, "strategy": strategy}


@app.post("/api/ai-strategies/{id}/verify")
def verify_ai_strategy(id: str):
    from src.db.repository import load_ai_strategies, record_ai_strategy_event, save_ai_strategies
    from src.strategy.predict import ModelPredictor
    import time

    strategies = load_ai_strategies()
    strategy = next((item for item in strategies if item["id"] == id), None)
    if not strategy:
        raise HTTPException(status_code=404, detail="Strategy not found")

    def persist_result(result: dict) -> dict:
        nonlocal strategy
        now = _now_kst_text()
        for item in strategies:
            if item["id"] == id:
                item["last_verified_at"] = now
                _store_validation_check(item, "api", result)
                if result.get("success") and item.get("status") == "draft":
                    item["status"] = "verified"
                strategy = item
                break
        save_ai_strategies(strategies)
        record_ai_strategy_event(id, "verified", result, strategy.get("strategy_version"))
        return result

    if strategy["provider"] == "none":
        return persist_result({"ok": True, "success": True, "speed_ms": 1, "message": "Rule/local strategy validation passed"})

    predictor = ModelPredictor(
        strategy_profile=strategy.get("profile") or {},
        description=strategy.get("description") or "",
    )
    predictor.enabled = True
    predictor.model_name = strategy["model"]
    # model_name을 전략 모델로 덮어썼으므로 캐시 시그니처를 재계산한다.
    predictor.strategy_signature = predictor._build_strategy_signature()

    test_features = {
        "strategy_score": 3.0,
        "rsi": 28.5,
        "rsi2": 12.0,
        "macd_hist": 0.5,
        "sma20_gap": 0.02,
        "sma60_gap": -0.01,
        "bb_position": -0.05,
        "return_5d": 0.01,
        "return_20d": -0.05,
        "volatility_20d": 0.02,
        "volume_ratio_20d": 1.6,
        "max_drawdown_20d": -0.08,
    }

    started_at = time.time()
    try:
        prediction = predictor.predict(test_features)
        duration_ms = int((time.time() - started_at) * 1000)
        if prediction.get("fallback_reason") and not prediction.get("ml_score"):
            return persist_result({
                "ok": True,
                "success": False,
                "speed_ms": duration_ms,
                "message": f"API validation failed: {prediction.get('fallback_reason')}",
            })
        return persist_result({
            "ok": True,
            "success": True,
            "speed_ms": duration_ms,
            "message": f"API validation passed. final_score={prediction.get('final_score')} ml_score={prediction.get('ml_score')}",
        })
    except Exception as exc:
        return persist_result({
            "ok": True,
            "success": False,
            "speed_ms": int((time.time() - started_at) * 1000),
            "message": f"Prediction error: {type(exc).__name__} - {exc}",
        })


@app.post("/api/ai-strategies/{id}/backtest")
def backtest_ai_strategy(id: str):
    from src.db.repository import load_ai_strategies, record_ai_strategy_event, save_ai_strategies

    strategies = load_ai_strategies()
    strategy = next((item for item in strategies if item["id"] == id), None)
    if not strategy:
        raise HTTPException(status_code=404, detail="Strategy not found")

    result = _build_strategy_backtest(strategy)
    now = _now_kst_text()
    for item in strategies:
        if item["id"] == id:
            item["last_backtested_at"] = now
            _store_validation_check(item, "backtest", result)
            if result.get("success"):
                item["status"] = "backtested"
            else:
                item["status"] = "review_required"
            strategy = item
            break
    save_ai_strategies(strategies)
    record_ai_strategy_event(id, "backtested", result, strategy.get("strategy_version"))
    return {"ok": True, "result": result, "strategy": strategy}


@app.post("/api/ai-strategies/{id}/evolve")
def evolve_ai_strategy(id: str):
    from src.strategy.evolve import evolve_strategy
    result = evolve_strategy(id)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("message", "Strategy evolution failed"))
    return {"ok": True, "result": result}


@app.post("/api/ai-strategies/{id}/paper/start")
def start_ai_strategy_paper(id: str):
    from src.db.repository import load_ai_strategies, record_ai_strategy_event, save_ai_strategies

    strategies = load_ai_strategies()
    strategy = next((item for item in strategies if item["id"] == id), None)
    if not strategy:
        raise HTTPException(status_code=404, detail="Strategy not found")
    if bool(getattr(trader.config, "ai_require_backtest_pass", True)) and not _check_passed(strategy, "backtest"):
        raise HTTPException(status_code=409, detail="Backtest must pass before paper trading")

    result = {"ok": True, "success": True, "status": "running", "started_at": _now_kst_text()}
    for item in strategies:
        if item["id"] == id:
            item["last_paper_started_at"] = result["started_at"]
            item["status"] = "paper_running"
            _store_validation_check(item, "paper_start", result)
            strategy = item
            break
    save_ai_strategies(strategies)
    record_ai_strategy_event(id, "paper_started", result, strategy.get("strategy_version"))
    return {"ok": True, "result": result, "strategy": strategy}


@app.post("/api/ai-strategies/{id}/paper/complete")
def complete_ai_strategy_paper(id: str, payload: PaperCompletePayload | None = None):
    from src.db.repository import load_ai_strategies, record_ai_strategy_event, save_ai_strategies

    payload = payload or PaperCompletePayload()
    strategies = load_ai_strategies()
    strategy = next((item for item in strategies if item["id"] == id), None)
    if not strategy:
        raise HTTPException(status_code=404, detail="Strategy not found")

    result = _paper_result_from_payload(payload, strategy)
    now = _now_kst_text()
    for item in strategies:
        if item["id"] == id:
            item["last_paper_completed_at"] = now
            _store_validation_check(item, "paper", result)
            item["status"] = "paper_passed" if result.get("success") else "review_required"
            strategy = item
            break
    save_ai_strategies(strategies)
    record_ai_strategy_event(id, "paper_completed", result, strategy.get("strategy_version"))
    return {"ok": True, "result": result, "strategy": strategy}


@app.post("/api/ai-strategies/{id}/approve")
def approve_ai_strategy(id: str):
    from src.db.repository import load_ai_strategies, record_ai_strategy_event, save_ai_strategies

    strategies = load_ai_strategies()
    found = None
    for strategy in strategies:
        if strategy["id"] == id:
            gate = _approval_gate(strategy)
            if not gate["ok"]:
                raise HTTPException(
                    status_code=409,
                    detail=f"Strategy approval blocked: missing {', '.join(gate['missing'])}",
                )
            strategy["status"] = "approved"
            found = strategy
            break
    if not found:
        raise HTTPException(status_code=404, detail="Strategy not found")
    save_ai_strategies(strategies)
    record_ai_strategy_event(id, "approved", {"gate": _approval_gate(found)}, found.get("strategy_version"))
    return {"ok": True, "strategy": found}


@app.post("/api/ai-strategies/{id}/retire")
def retire_ai_strategy(id: str):
    from src.db.repository import load_ai_strategies, record_ai_strategy_event, save_ai_strategies

    strategies = load_ai_strategies()
    found = None
    for strategy in strategies:
        if strategy["id"] == id:
            strategy["status"] = "retired"
            strategy["selected"] = False
            found = strategy
            break
    if not found:
        raise HTTPException(status_code=404, detail="Strategy not found")
    save_ai_strategies(strategies)
    record_ai_strategy_event(id, "retired", {}, found.get("strategy_version"))
    return {"ok": True, "strategy": found}


@app.get("/api/ai-strategies/{id}/events")
def get_ai_strategy_events(id: str, limit: int = 100):
    from src.db.repository import get_ai_strategy_events, load_ai_strategies

    if not any(strategy["id"] == id for strategy in load_ai_strategies()):
        raise HTTPException(status_code=404, detail="Strategy not found")
    return {"events": get_ai_strategy_events(id, limit=limit)}


@app.get("/api/ai-strategies/{id}/performance")
def get_ai_strategy_performance(id: str, days: int = 30):
    from src.db.repository import (
        get_ai_strategy_performance as load_performance,
        load_ai_strategies,
        refresh_scanned_candidate_forward_returns,
    )

    if not any(strategy["id"] == id for strategy in load_ai_strategies()):
        raise HTTPException(status_code=404, detail="Strategy not found")
    refresh_scanned_candidate_forward_returns(limit=500)
    return load_performance(id, days=days)


@app.post("/api/ai-strategies/{id}/performance/review")
def review_ai_strategy_performance(id: str, days: int = 30):
    from src.db.repository import load_ai_strategies, review_ai_strategy_performance as review_performance

    if not any(strategy["id"] == id for strategy in load_ai_strategies()):
        raise HTTPException(status_code=404, detail="Strategy not found")
    return review_performance(id, days=days)




@app.get("/api/watchlist")
def get_watchlist():
    from src.db.repository import load_watchlist_data, get_watchlist_extra_info
    from src.strategy.seven_split import STOCK_NAMES, STOCK_SECTORS
    data = load_watchlist_data()
    symbols_detail = []
    for code in data.get("symbols", []):
        extra = get_watchlist_extra_info(code)
        symbols_detail.append({
            "symbol": code,
            "name": STOCK_NAMES.get(code, "알 수 없는 종목"),
            "sector": STOCK_SECTORS.get(code, "미분류"),
            "price": extra["price"],
            "score": extra["score"],
            "reason": extra["reason"],
            "change_rate": extra["change_rate"],
            "rsi": extra["rsi"],
            "updated_at": extra["updated_at"]
        })
    return {
        "symbols": symbols_detail,
        "ai_auto_add": data.get("ai_auto_add", False),
        "ai_auto_add_threshold": data.get("ai_auto_add_threshold", 3.0)
    }



@app.post("/api/watchlist")
def add_to_watchlist(payload: WatchlistAddPayload):
    from src.db.repository import load_watchlist_data, save_watchlist_data
    from src.strategy.seven_split import sync_watchlist_runtime, STOCK_NAMES
    
    code = payload.symbol.strip()
    if not code.isdigit() or len(code) != 6:
        raise HTTPException(status_code=400, detail="유효하지 않은 종목코드 형식입니다. (6자리 숫자)")
        
    data = load_watchlist_data()
    if code in data["symbols"]:
        raise HTTPException(status_code=400, detail="이미 관심목록에 등록되어 있는 종목입니다.")
        
    data["symbols"].append(code)
    save_watchlist_data(data)
    sync_watchlist_runtime()
    
    return {
        "ok": True,
        "symbol": code,
        "name": STOCK_NAMES.get(code, "알 수 없는 종목")
    }



@app.delete("/api/watchlist/{symbol}")
def delete_from_watchlist(symbol: str):
    from src.db.repository import load_watchlist_data, save_watchlist_data
    from src.strategy.seven_split import sync_watchlist_runtime
    
    code = symbol.strip()
    data = load_watchlist_data()
    if code not in data["symbols"]:
        raise HTTPException(status_code=404, detail="관심목록에 없는 종목입니다.")
        
    data["symbols"].remove(code)
    save_watchlist_data(data)
    sync_watchlist_runtime()
    
    return {"ok": True}



@app.post("/api/watchlist/toggle-auto")
def toggle_watchlist_auto_add(payload: WatchlistTogglePayload):
    from src.db.repository import load_watchlist_data, save_watchlist_data
    
    data = load_watchlist_data()
    data["ai_auto_add"] = payload.enabled
    if payload.threshold is not None:
        data["ai_auto_add_threshold"] = payload.threshold
    save_watchlist_data(data)
    
    return {
        "ok": True,
        "ai_auto_add": data["ai_auto_add"],
        "ai_auto_add_threshold": data.get("ai_auto_add_threshold", 3.0)
    }




@app.get("/api/ai-allocation")
def get_ai_allocation():
    missing = _required_env_missing()
    if missing:
        raise HTTPException(status_code=503, detail=f"Missing environment variables: {', '.join(missing)}")

    def _build():
        api = _get_api()
        parsed = _parse_balance(_get_balance_data(api))
        from src.db.repository import load_ai_strategies

        strategies = load_ai_strategies()
        active_strategy = next((strategy for strategy in strategies if strategy.get("selected")), None)
        holdings = []
        for holding in parsed["holdings"]:
            daily = api.get_daily(holding["symbol"], n=120)
            prices = [float(row["stck_clpr"]) for row in daily if row.get("stck_clpr")]
            highs = [float(row["stck_hgpr"]) for row in daily if row.get("stck_hgpr")]
            volumes = [float(row["acml_vol"]) for row in daily if row.get("acml_vol")]
            prices.reverse()
            highs.reverse()
            volumes.reverse()
            holdings.append({
                "symbol": holding["symbol"],
                "name": holding["name"],
                "qty": holding["qty"],
                "price": holding["price"],
                "value": holding["value"],
                "prices": prices,
                "highs": highs,
                "volumes": volumes,
            })
        plan = trader.generate_ai_weight_plan(holdings, parsed["total_eval"])
        if active_strategy:
            for position in plan.get("positions", []):
                position["strategy_id"] = active_strategy.get("id")
                position["strategy_version"] = active_strategy.get("strategy_version")
                position["profile_hash"] = active_strategy.get("profile_hash")
                position["ai_strategy_name"] = active_strategy.get("name")
        return plan

    try:
        return snapshot_read_through("ai_allocation", _build)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"AI allocation failed: {e}") from e




@app.get("/api/finrl/status")
def get_finrl_status():
    return _vendor_status("finrl", VENDOR_PROJECTS["finrl"])




@app.get("/api/vendors")
def get_vendors():
    return {"vendors": [_vendor_status(slug, meta) for slug, meta in VENDOR_PROJECTS.items()]}




@app.get("/api/vendors/{slug}")
def get_vendor(slug: str):
    if slug not in VENDOR_PROJECTS:
        raise HTTPException(status_code=404, detail="vendor not found")
    return _vendor_status(slug, VENDOR_PROJECTS[slug])




@app.get("/api/finrl/pipeline")
def get_finrl_pipeline():
    return {
        "pipeline": [
            {
                "stage": "Data",
                "source": "KIS balance + KIS daily chart",
                "finrl_reference": "meta/data_processor.py",
                "status": "adapted",
            },
            {
                "stage": "Feature Engineering",
                "source": "RSI, RSI2, SMA, Bollinger, MACD, volatility",
                "finrl_reference": "meta/preprocessor/preprocessors.py",
                "status": "adapted",
            },
            {
                "stage": "Environment",
                "source": "current portfolio snapshot",
                "finrl_reference": "meta/env_stock_trading/env_stocktrading.py",
                "status": "dashboard proxy",
            },
            {
                "stage": "Agent Policy",
                "source": "deterministic weight policy inspired by FinRL-X",
                "finrl_reference": "agents/stablebaselines3/models.py",
                "status": "lightweight adapter",
            },
            {
                "stage": "Execution",
                "source": "approval queue + KIS order API",
                "finrl_reference": "trade.py",
                "status": "protected by DRY_RUN and approval",
            },
        ],
    }







@app.get("/api/approvals")
def get_approvals(limit: int = 50):
    if limit < 1:
        raise HTTPException(status_code=400, detail="limit must be greater than 0")
    limit = min(limit, 200)

    _init_approval_db()
    with trader.connect_db() as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM approvals ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return {"approvals": [_approval_row(row) for row in rows]}




@app.post("/api/approvals")
def create_approval(payload: dict = Body(...)):
    action = str(payload.get("action", "")).lower()
    if action not in {"buy", "sell"}:
        raise HTTPException(status_code=400, detail="action must be buy or sell")

    symbol = str(payload.get("symbol", "")).strip()
    if not symbol:
        raise HTTPException(status_code=400, detail="symbol is required")

    qty = _to_int(payload.get("qty"))
    if qty <= 0:
        raise HTTPException(status_code=400, detail="qty must be greater than 0")

    price = _to_int(payload.get("price"))
    name = str(payload.get("name") or symbol)
    reason = str(payload.get("reason") or "")
    source = str(payload.get("source") or "dashboard")
    strategy_id = str(payload.get("strategy_id") or "").strip() or None
    strategy_version = _to_int(payload.get("strategy_version")) or None
    profile_hash = str(payload.get("profile_hash") or "").strip() or None
    source_candidate_id = _to_int(payload.get("source_candidate_id")) or None
    now = trader.datetime.now(trader.KST).strftime("%Y-%m-%d %H:%M:%S")

    _init_approval_db()
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
                now, now, symbol, name, action, qty, price, reason, source,
                strategy_id, strategy_version, profile_hash, source_candidate_id,
            ),
        )
        approval_id = cursor.lastrowid
    if _auto_approval_enabled():
        result = _approve_pending_approval(approval_id, "자동승인")
        result["auto_approved"] = True
        return result
    return {"id": approval_id, "status": "pending"}




@app.post("/api/holdings/sell-all")
def sell_all_holdings(payload: dict | None = Body(default=None)):
    missing = _required_env_missing()
    if missing:
        raise HTTPException(status_code=503, detail=f"Missing environment variables: {', '.join(missing)}")

    try:
        api = _get_api()
        parsed = _parse_balance(_get_balance_data(api, allow_cache=False))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"KIS balance API request failed: {e}") from e

    orders = []
    for holding in parsed.get("holdings", []):
        symbol = str(holding.get("symbol", "")).strip()
        qty = _to_int(holding.get("qty"))
        if not symbol or qty <= 0:
            continue
        orders.append({
            "symbol": symbol,
            "name": str(holding.get("name") or symbol),
            "action": "sell",
            "qty": qty,
            "price": 0,
            "reason": "dashboard sell all holdings",
            "source": "dashboard_sell_all",
        })

    if not orders:
        return {"status": "empty", "created_count": 0, "orders": []}

    created = [create_approval(order) for order in orders]
    _clear_balance_cache()

    return {
        "status": "created",
        "created_count": len(created),
        "pending_count": sum(1 for item in created if isinstance(item, dict) and item.get("status") == "pending"),
        "executed_count": sum(1 for item in created if isinstance(item, dict) and item.get("status") == "executed"),
        "failed_count": sum(1 for item in created if isinstance(item, dict) and item.get("status") == "failed"),
        "auto_approved": any(item.get("auto_approved") for item in created if isinstance(item, dict)),
        "orders": created,
    }




@app.post("/api/approvals/{approval_id}/approve")
def approve_order(approval_id: int):
    return _approve_pending_approval(approval_id, "수동승인")




@app.post("/api/approvals/{approval_id}/reject")
def reject_order(approval_id: int):
    _load_pending_approval(approval_id)
    now = trader.datetime.now(trader.KST).strftime("%Y-%m-%d %H:%M:%S")
    with trader.connect_db() as conn:
        conn.execute(
            "UPDATE approvals SET status = 'rejected', response_msg = 'Rejected by dashboard', updated_at = ? WHERE id = ?",
            (now, approval_id),
        )
    return {"id": approval_id, "status": "rejected"}




@app.post("/api/trades/order-status/sync")
def sync_trade_order_status(days: int = 30):
    if trader.DRY_RUN:
        raise HTTPException(status_code=400, detail="Order status sync requires DRY_RUN=false")
    try:
        result = _sync_order_status_from_history(_get_api(), days=days)
        _clear_balance_cache()
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e




@app.post("/api/trades/sync")
def sync_trades(days: int = 90):
    if trader.DRY_RUN:
        raise HTTPException(status_code=400, detail="紐⑥쓽 ?ㅽ뻾(DRY_RUN) 紐⑤뱶?먯꽌??利앷텒??怨꾩쥖 ?숆린?붾? ?ъ슜?????놁뒿?덈떎.")
    try:
        api = _get_api()
        history_sync = None
        history_error = None
        try:
            history_sync = _sync_filled_trades_from_history(api, days=days)
        except Exception as exc:
            history_error = str(exc)

        balance_data = _get_balance_data(api, allow_cache=False)
        parsed_balance = _parse_balance(balance_data)
        current_holdings = {h['symbol']: h for h in parsed_balance['holdings']}
        
        # Reconstruct current holdings from DB and Cloud
        cloud_trades = fetch_cloud_trades() or []
        local_trades = []
        with trader.connect_db() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("SELECT * FROM trades ORDER BY ts ASC").fetchall()
            local_trades = [dict(row) for row in rows]
            
        merged_trades = {}
        for t in cloud_trades + local_trades:
            ts = t.get("ts") or t.get("timestamp")
            if not ts: continue
            key = f"{ts}_{t.get('symbol')}_{t.get('action')}"
            merged_trades[key] = t
            
        trades = _account_trades(sorted(merged_trades.values(), key=lambda x: x.get("ts", "")))
        
        db_holdings = {}
        names = {}
        for t in trades:
            if not t.get("ok", False): continue
            sym = t["symbol"]
            qty = t["qty"]
            names[sym] = t.get("name", sym)
            if sym not in db_holdings:
                db_holdings[sym] = 0
            if t["action"] == "buy":
                db_holdings[sym] += qty
            elif t["action"] == "sell":
                db_holdings[sym] = max(0, db_holdings[sym] - qty)
                
        synced_count = 0
        
        # 1. Sync missing buys (broker has more)
        for sym, ch in current_holdings.items():
            broker_qty = ch["qty"]
            db_qty = db_holdings.get(sym, 0)
            diff = broker_qty - db_qty
            
            if diff != 0:
                action = "buy" if diff > 0 else "sell"
                raw_stock = ch.get("_raw", {})
                price = int(float(raw_stock.get("pchs_avg_pric", ch["price"])))
                
                trader.save_trade(
                    symbol=sym,
                    name=ch["name"],
                    action=action,
                    qty=abs(diff),
                    price=price,
                    reason="利앷텒???붽퀬 媛뺤젣 ?숆린??(?섎룞/?꾨씫遺?蹂댁젙)",
                    ok=True,
                    order_submission_enabled=True
                )
                synced_count += 1
                
        # Calculate db average costs to use for selling missing items without affecting PnL
        db_costs = {}
        for t in trades:
            if not t.get("ok", False): continue
            sym = t["symbol"]
            qty = t["qty"]
            price = t["price"]
            if sym not in db_costs: db_costs[sym] = {"qty": 0, "cost": 0.0}
            if t["action"] == "buy":
                total_qty = db_costs[sym]["qty"] + qty
                total_cost = (db_costs[sym]["qty"] * db_costs[sym]["cost"]) + (qty * price)
                db_costs[sym]["qty"] = total_qty
                db_costs[sym]["cost"] = total_cost / total_qty if total_qty > 0 else 0
            elif t["action"] == "sell":
                db_costs[sym]["qty"] = max(0, db_costs[sym]["qty"] - qty)
                if db_costs[sym]["qty"] <= 0: db_costs[sym]["cost"] = 0

        # 2. Sync missing sells (broker has less or none)
        for sym, db_qty in db_holdings.items():
            if db_qty > 0 and sym not in current_holdings:
                avg_cost = int(db_costs.get(sym, {}).get("cost", 0))
                trader.save_trade(
                    symbol=sym,
                    name=names.get(sym, sym),
                    action="sell",
                    qty=db_qty,
                    price=avg_cost,  # Use avg_cost to avoid distorting Realized PnL

                    reason="利앷텒???붽퀬 媛뺤젣 ?숆린??(?꾨웾留ㅻ룄 蹂댁젙)",
                    ok=True,
                    order_submission_enabled=True
                )
                synced_count += 1
                
        imported_count = _to_int(history_sync.get("imported_count")) if history_sync else 0
        updated_count = _to_int(history_sync.get("updated_count")) if history_sync else 0
        # 동기화로 보유/거래가 바뀌었으니 잔고·파생 보유탭 스냅샷을 무효화해 현행화한다.
        _clear_balance_cache()
        return {
            "ok": True,
            "synced_count": synced_count + imported_count,
            "balance_synced_count": synced_count,
            "history_imported_count": imported_count,
            "history_updated_count": updated_count,
            "history_sync": history_sync,
            "history_error": history_error,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))



@app.get("/api/trades")
def get_trades(limit: int = 50):
    try:
        cloud_trades = fetch_cloud_trades() or []
        local_trades = []
        with trader.connect_db() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("SELECT * FROM trades ORDER BY ts ASC").fetchall()
            local_trades = [dict(row) for row in rows]
            
        merged_trades = {}
        for t in cloud_trades + local_trades:
            ts = t.get("ts") or t.get("timestamp")
            if not ts: continue
            key = f"{ts}_{t.get('symbol')}_{t.get('action')}"
            merged_trades[key] = {
                "ts": ts,
                "symbol": t.get("symbol"),
                "name": t.get("name", t.get("symbol")),
                "action": t.get("action"),
                "qty": t.get("qty", 0),
                "price": t.get("price", 0),
                "reason": t.get("reason", ""),
                "ok": t.get("ok", 1),
                "env": t.get("env", "demo"),
                "dry_run": t.get("dry_run", 0),
                "broker_order_id": t.get("broker_order_id", ""),
                "order_status": t.get("order_status", ""),
                "filled_qty": _to_int(t.get("filled_qty")),
                "filled_price": _to_int(t.get("filled_price")),
                "response_msg": t.get("response_msg", ""),
                "strategy_id": t.get("strategy_id", ""),
                "strategy_version": t.get("strategy_version"),
                "profile_hash": t.get("profile_hash", ""),
                "source_approval_id": t.get("source_approval_id"),
            }
            
        trades = sorted(_account_trades(list(merged_trades.values())), key=lambda x: x["ts"], reverse=True)
        return {"trades": trades[:limit]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))




@app.get("/api/performance/periodic")
def get_periodic_performance():
    try:
        trades = _load_merged_trades()
        return _build_periodic_performance(trades)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))




@app.get("/api/performance")
def get_performance():
    try:
        trades = _account_trades(_load_merged_trades())
        
        total_trades = len(trades)
        success_count = sum(1 for t in trades if t.get("ok", False))
        success_rate = (success_count / total_trades * 100) if total_trades > 0 else 0
        
        holdings = {}
        realized_pnl = 0
        names = {}
        
        for t in trades:
            if not t.get("ok", False): continue
            sym = t["symbol"]
            qty = t["qty"]
            price = t["price"]
            
            # Skip invalid qty or price <= 0 trades to avoid avg_cost and realized_pnl distortion
            if qty <= 0 or price <= 0:
                continue
                
            names[sym] = t.get("name", sym)
            
            if sym not in holdings:
                holdings[sym] = {"qty": 0, "cost": 0.0}
                
            if t["action"] == "buy":
                total_qty = holdings[sym]["qty"] + qty
                total_cost = (holdings[sym]["qty"] * holdings[sym]["cost"]) + (qty * price)
                holdings[sym]["qty"] = total_qty
                holdings[sym]["cost"] = total_cost / total_qty if total_qty > 0 else 0
            elif t["action"] == "sell":
                sell_qty = min(qty, holdings[sym]["qty"])
                profit = (price - holdings[sym]["cost"]) * sell_qty
                realized_pnl += profit
                holdings[sym]["qty"] -= sell_qty
                if holdings[sym]["qty"] <= 0:
                    holdings[sym]["qty"] = 0
                    holdings[sym]["cost"] = 0
                    
        # Explicitly calculate realized_pnl by summing daily periodic performance values to match daily performance view exactly
        try:
            periodic_perf = _build_periodic_performance(trades)
            realized_pnl = sum(day["realized_pnl"] for day in periodic_perf.get("daily", []))
        except Exception:
            pass
                    
        # Fetch current prices to calculate evaluation PnL
        current_holdings = {}
        total_broker_pnl = 0
        try:
            api = _get_api()
            balance_data = _get_balance_data(api)
            parsed_balance = _parse_balance(balance_data)
            current_holdings = {h['symbol']: h for h in parsed_balance['holdings']}
            total_broker_pnl = parsed_balance.get("pnl", 0)
        except Exception:
            pass

        # ?ъ슜???붿껌: 遺덉씪移섍? 諛쒖깮?섎㈃ 利앷텒???뺣낫濡?留욎떠??蹂댁젙
        # ?먮룞留ㅻℓ 湲곕줉(trades.json)?쇰줈 異붿쟻??蹂댁쑀????? 利앷텒???ㅼ젣 ?붽퀬瑜?媛뺤젣濡???뼱?뚯? (?? DRY_RUN???뚮뒗 DB ?곗꽑)
        eval_details = []
        total_eval_pnl = total_broker_pnl
        
        if trader.DRY_RUN:
            total_eval_pnl = 0
            for sym, data in holdings.items():
                if data["qty"] > 0:
                    current_price = data["cost"]
                    if sym in current_holdings:
                        current_price = current_holdings[sym]["price"]
                    else:
                        try:
                            q = api.get_quote(sym)
                            current_price = q["current"]
                        except Exception:
                            pass
                    
                    eval_pnl = (current_price - data["cost"]) * data["qty"]
                    return_rate = ((current_price / data["cost"]) - 1) * 100 if data["cost"] > 0 else 0
                    total_eval_pnl += eval_pnl
                    
                    eval_details.append({
                        "symbol": sym,
                        "name": names.get(sym, sym),
                        "qty": data["qty"],
                        "avg_cost": data["cost"],
                        "current_price": current_price,
                        "eval_pnl": int(eval_pnl),
                        "return_rate": round(return_rate, 2),
                        "broker_qty": current_holdings.get(sym, {}).get("qty", 0),
                        "broker_pnl": int(current_holdings.get(sym, {}).get("pnl", 0)),
                        "diff_reason": "DRY_RUN"
                    })
        else:
            for sym, ch in current_holdings.items():
                raw_stock = ch.get("_raw", {})
                avg_cost = float(raw_stock.get("pchs_avg_pric", 0)) if raw_stock.get("pchs_avg_pric") else 0
                
                if avg_cost == 0 and ch["qty"] > 0:
                    avg_cost = ch["price"] - (ch["pnl"] / ch["qty"])
                    
                recorded_qty = holdings.get(sym, {}).get("qty", 0)
                diff_reason = ""
                if recorded_qty == 0:
                    diff_reason = "수동매수/기록누락 보정 완료"
                elif recorded_qty != ch["qty"]:
                    diff_reason = f"수량 불일치 {recorded_qty}주->{ch['qty']}주 보정 완료"
                    
                return_rate = ((ch["price"] / avg_cost) - 1) * 100 if avg_cost > 0 else 0.0
                eval_details.append({
                    "symbol": sym,
                    "name": ch["name"],
                    "qty": ch["qty"],
                    "avg_cost": avg_cost,
                    "current_price": ch["price"],
                    "eval_pnl": int(ch["pnl"]),
                    "return_rate": round(return_rate, 2),
                    "broker_qty": ch["qty"],
                    "broker_pnl": int(ch["pnl"]),
                    "diff_reason": diff_reason
                })

        untracked_details = [] # ???댁긽 ?ъ슜?섏? ?딆쓬 (紐⑤몢 eval_details濡??≪닔)
                    
        return {
            "total_trades": total_trades,
            "success_rate": round(success_rate, 2),
            "realized_pnl": int(realized_pnl),
            "total_eval_pnl": int(total_eval_pnl),
            "total_broker_pnl": int(total_broker_pnl),
            "eval_details": eval_details,
            "untracked_details": untracked_details
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))



@app.get("/api/risk/status")
def get_risk_status():
    def _build():
        api = _get_api()
        balance_data = _get_balance_data(api, allow_cache=True)
        parsed = _parse_balance(balance_data)

        total_capital = trader.TOTAL_CAPITAL
        pnl = parsed.get("pnl", 0)
        loss_pct = abs(pnl) / total_capital * 100 if total_capital > 0 and pnl < 0 else 0
        max_daily_loss = getattr(trader.config, "max_daily_loss_pct", 3.0)

        return {
            "total_capital": total_capital,
            "current_total": parsed.get("total_eval", 0),
            "stock_eval": parsed.get("stock_eval", 0),
            "cash": parsed.get("cash", 0),
            "cash_ratio": parsed.get("cash_ratio", 0),
            "stock_ratio": parsed.get("stock_ratio", 0),
            "daily_pnl": pnl,
            "daily_loss_pct": round(loss_pct, 2),
            "max_daily_loss_pct": max_daily_loss,
            "loss_halt": loss_pct >= max_daily_loss,
        }

    try:
        result = snapshot_read_through("risk_status", _build)
        # kill_switch는 로컬 상태라 stale 스냅샷에도 항상 현재값을 덮어쓴다.
        result["halted"] = bool(result.get("loss_halt")) or Path(".runtime/kill_switch.json").exists()
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))



@app.get("/api/decisions/history")
def get_decision_history(limit: int = 50):
    try:
        with trader.connect_db() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("SELECT * FROM decision_logs ORDER BY ts DESC LIMIT ?", (limit,)).fetchall()
            logs = [dict(row) for row in rows]
            for log in logs:
                if isinstance(log.get("indicators"), str):
                    try:
                        log["indicators"] = json.loads(log["indicators"])
                    except:
                        pass
            return {"decisions": logs}
    except Exception as e:
        return {"decisions": []}



@app.post("/api/system/kill")
def activate_kill_switch():
    kill_file = Path(".runtime/kill_switch.json")
    kill_file.parent.mkdir(parents=True, exist_ok=True)
    with open(kill_file, "w") as f:
        json.dump({"active": True, "ts": trader.datetime.now(trader.KST).isoformat()}, f)
    return {"ok": True, "msg": "Kill switch activated"}



@app.post("/api/system/unkill")
def deactivate_kill_switch():
    kill_file = Path(".runtime/kill_switch.json")
    if kill_file.exists():
        kill_file.unlink()
    return {"ok": True, "msg": "Kill switch deactivated"}




@app.get("/api/scheduler/status")
def get_scheduler_status():
    global _scheduler_run_state
    
    config = {
        "cron_tz": os.environ.get("HANSTOCK_CRON_TZ", "Asia/Seoul"),
        "daily_auto_retries": os.environ.get("HANSTOCK_DAILY_AUTO_RETRIES", "3"),
        "daily_auto_retry_delay_seconds": os.environ.get("HANSTOCK_DAILY_AUTO_RETRY_DELAY_SECONDS", "10"),
        "scheduler_retries": os.environ.get("HANSTOCK_SCHEDULER_RETRIES", "1"),
        "scheduler_retry_delay_seconds": os.environ.get("HANSTOCK_SCHEDULER_RETRY_DELAY_SECONDS", "5"),
        "slack_enabled": os.environ.get("HANSTOCK_SCHEDULER_SLACK", "true"),
        "sync_enabled": os.environ.get("HANSTOCK_ORDER_STATUS_SYNC", "true"),
        "result_path": os.environ.get("HANSTOCK_SCHEDULER_RESULT_PATH", ".runtime/daily_auto_last_result.json"),
        "trading_env": trader.TRADING_ENV,
        "dry_run": trader.DRY_RUN,
        "order_submission": trader.ORDER_SUBMISSION_ENABLED,
    }
    
    last_result = None
    try:
        from src.db.repository import load_today_scheduler_results, load_latest_scheduler_result
        last_result = load_today_scheduler_results()
        if last_result is None:
            last_result = load_latest_scheduler_result()
    except Exception:
        pass
        
    if last_result is None:
        path = Path(config["result_path"])
        if path.exists():
            try:
                last_result = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                pass
            
    active_strategy_id = "seven_split"
    active_strategy_name = "기본 룰베이스 (Seven Split)"
    try:
        from src.db.repository import load_ai_strategies
        active = next((s for s in load_ai_strategies() if s.get("selected")), None)
        if active:
            active_strategy_id = active.get("model") or "seven_split"
            active_strategy_name = active.get("name") or active_strategy_id
    except Exception:
        pass

    return {
        "config": config,
        "last_result": last_result,
        "run_state": _scheduler_run_state,
        "active_strategy_id": active_strategy_id,
        "active_strategy_name": active_strategy_name,
    }




@app.post("/api/scheduler/run")
def trigger_scheduler_run(payload: dict = Body(...)):
    global _scheduler_run_state
    mode = str(payload.get("mode", "daily_auto")).lower()
    if mode not in {"daily_auto", "execute", "analysis_only"}:
        raise HTTPException(
            status_code=400,
            detail=f"지원하지 않는 국내장 스케줄러 모드입니다: '{mode}'. 'daily_auto', 'execute', 'analysis_only' 중 하나를 선택해 주세요."
        )
        
    include_ai_rebalance = bool(payload.get("include_ai_rebalance", True))
    auto_approve = bool(payload.get("auto_approve", mode == "daily_auto"))

    # 실행 대상 전략: payload.strategy_id가 있으면 사용, 없으면 현재 선택된 전략을 강제.
    force_strategy_id = payload.get("strategy_id")
    if force_strategy_id is not None:
        force_strategy_id = str(force_strategy_id).strip() or None
    if force_strategy_id is None:
        try:
            from src.db.repository import load_ai_strategies
            active = next((s for s in load_ai_strategies() if s.get("selected")), None)
            # model이 "none"(룰 전용)인 경우 scheduler.py와 동일하게 seven_split로 폴백되도록 None 유지.
            if active and active.get("model") and active.get("model") != "none":
                force_strategy_id = active.get("model")
        except Exception:
            force_strategy_id = None

    with _scheduler_running_lock:
        if _scheduler_run_state["is_running"]:
            raise HTTPException(status_code=409, detail="스케줄러가 이미 실행 중입니다.")

        _scheduler_run_state["is_running"] = True
        _scheduler_run_state["mode"] = mode
        _scheduler_run_state["strategy_id"] = force_strategy_id
        _scheduler_run_state["started_at"] = trader.datetime.now(trader.KST).isoformat()
        _scheduler_run_state["completed_at"] = None
        _scheduler_run_state["result"] = None
        _scheduler_run_state["error"] = None

    t = threading.Thread(
        target=_bg_run_scheduled_cycle,
        args=(mode, include_ai_rebalance, auto_approve, force_strategy_id),
        daemon=True
    )
    t.start()
    return {"status": "started", "mode": mode, "strategy_id": force_strategy_id}
