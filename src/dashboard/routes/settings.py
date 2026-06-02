# -*- coding: utf-8 -*-
from fastapi import Body, HTTPException, Request
from fastapi.responses import FileResponse
import src.dashboard.core as _core
from src.dashboard.core import *
globals().update({k: v for k, v in _core.__dict__.items() if not k.startswith('__')})

ENV_FIELD_TEXT = {
    "KISTOCK_APP_KEY": {"label": "KIS App Key", "hint": "국내주식 KIS API 앱 키입니다."},
    "KISTOCK_APP_SECRET": {"label": "KIS App Secret", "hint": "국내주식 KIS API 앱 시크릿입니다."},
    "KISTOCK_ACCOUNT": {"label": "KIS 계좌번호", "hint": "8자리 또는 10자리 계좌번호를 입력합니다."},
    "TRADING_ENV": {"label": "거래 환경", "hint": "demo=모의투자, real=실전투자 환경입니다."},
    "DRY_RUN": {"label": "주문 차단 모드", "hint": "true이면 실제 KIS 주문 API를 호출하지 않습니다."},
    "ENABLE_LIVE_TRADING": {"label": "실전 주문 허용", "hint": "실전 환경에서 실제 주문을 허용하는 최종 보호 스위치입니다."},
    "REQUIRE_APPROVAL": {"label": "주문 승인 필요", "hint": "true이면 주문을 승인 대기열에 먼저 등록합니다."},
    "SPLIT_N": {"label": "분할 매수 횟수"},
    "STOP_LOSS_PCT": {"label": "손절 기준 %"},
    "TAKE_PROFIT": {"label": "익절 기준 %"},
    "RSI_BUY": {"label": "RSI 매수 기준"},
    "RSI_SELL": {"label": "RSI 매도 기준"},
    "TOTAL_CAPITAL": {"label": "총 운용 자금"},
    "MAX_POSITIONS": {"label": "최대 보유 종목 수"},
    "MAX_SINGLE_WEIGHT": {"label": "종목당 최대 비중"},
    "CASH_BUFFER": {"label": "현금 보유 비중"},
    "MAX_DAILY_LOSS_PCT": {"label": "일 최대 손실 %"},
    "SCAN_UNIVERSE_SIZE": {"label": "스캔 종목 수"},
    "KIS_CIRCUIT_COOLDOWN_SECONDS": {"label": "KIS API 차단 해제 대기초", "hint": "KIS API 오류가 반복될 때 재시도 전 대기 시간입니다."},
    "TRADE_DB_PATH": {"label": "거래 DB 경로"},
    "ACTIVE_MODEL_VERSION": {"label": "활성 모델 버전"},
    "AI_STRATEGY_ENABLED": {"label": "AI 전략 사용", "hint": "true이면 후보 평가에 OpenAI 모델 점수를 함께 사용합니다."},
    "AI_SCORE_WEIGHT": {"label": "AI 점수 반영 비중", "hint": "0~1 사이 값입니다. 0.4이면 룰 60%, AI 40%로 계산합니다."},
    "AI_MIN_MODEL_CONFIDENCE": {"label": "AI 최소 신뢰도"},
    "AI_REQUIRE_BACKTEST_PASS": {"label": "백테스트 통과 필수"},
    "AI_AUTO_APPROVE": {"label": "AI 자동 승인"},
    "OPENAI_API_KEY": {"label": "OpenAI API Key", "hint": "gpt-5-mini 호출에 사용할 OpenAI API 키입니다."},
    "OPENAI_MODEL": {"label": "OpenAI 모델", "hint": "예: gpt-5-mini"},
    "OPENAI_TIMEOUT_SECONDS": {"label": "OpenAI 응답 제한초"},
    "AI_CANDIDATE_LIMIT": {"label": "AI 평가 후보 수"},
    "SLACK_WEBHOOK_URL": {"label": "Slack Webhook URL"},
    "TELEGRAM_API_ID": {"label": "Telegram API ID"},
    "TELEGRAM_API_HASH": {"label": "Telegram API Hash"},
    "TELEGRAM_SESSION_NAME": {"label": "Telegram Session Name", "hint": "로컬 Telethon 세션 경로입니다. Git에 포함하지 마세요."},
    "TELEGRAM_TARGET_CHANNELS": {"label": "Telegram Target Channels", "hint": "쉼표로 구분한 채널 사용자명, ID, 초대 링크입니다."},
}


def _current_env_field_value(key: str, raw_values: dict[str, str]) -> str:
    if key in raw_values:
        return raw_values.get(key, "")
    runtime_values = {
        "TRADING_ENV": getattr(trader.config, "trading_env", trader.TRADING_ENV),
        "DRY_RUN": str(bool(getattr(trader.config, "dry_run", trader.DRY_RUN))).lower(),
        "ENABLE_LIVE_TRADING": str(bool(getattr(trader.config, "enable_live_trading", trader.ENABLE_LIVE_TRADING))).lower(),
        "REQUIRE_APPROVAL": str(bool(getattr(trader.config, "require_approval", trader.REQUIRE_APPROVAL))).lower(),
        "SPLIT_N": getattr(trader.config, "split_n", trader.SPLIT_N),
        "STOP_LOSS_PCT": getattr(trader.config, "stop_loss_pct", trader.STOP_LOSS_PCT),
        "TAKE_PROFIT": getattr(trader.config, "take_profit", trader.TAKE_PROFIT),
        "RSI_BUY": getattr(trader.config, "rsi_buy", trader.RSI_BUY),
        "RSI_SELL": getattr(trader.config, "rsi_sell", trader.RSI_SELL),
        "TOTAL_CAPITAL": getattr(trader.config, "total_capital", trader.TOTAL_CAPITAL),
        "MAX_POSITIONS": getattr(trader.config, "max_positions", trader.MAX_POSITIONS),
        "MAX_SINGLE_WEIGHT": getattr(trader.config, "max_single_weight", trader.MAX_SINGLE_WEIGHT),
        "CASH_BUFFER": getattr(trader.config, "cash_buffer", trader.CASH_BUFFER),
        "MAX_DAILY_LOSS_PCT": getattr(trader.config, "max_daily_loss_pct", trader.MAX_DAILY_LOSS_PCT),
        "SCAN_UNIVERSE_SIZE": getattr(trader.config, "scan_universe_size", trader.SCAN_UNIVERSE_SIZE),
        "KIS_CIRCUIT_COOLDOWN_SECONDS": getattr(trader.config, "kis_circuit_cooldown_seconds", ""),
        "TRADE_DB_PATH": getattr(trader.config, "trade_db_path", ""),
        "ACTIVE_MODEL_VERSION": getattr(trader.config, "active_model_version", ""),
        "AI_STRATEGY_ENABLED": str(bool(getattr(trader.config, "ai_strategy_enabled", False))).lower(),
        "AI_SCORE_WEIGHT": getattr(trader.config, "ai_score_weight", 0.4),
        "AI_MIN_MODEL_CONFIDENCE": getattr(trader.config, "ai_min_model_confidence", 0.6),
        "AI_REQUIRE_BACKTEST_PASS": str(bool(getattr(trader.config, "ai_require_backtest_pass", True))).lower(),
        "AI_AUTO_APPROVE": str(bool(getattr(trader.config, "ai_auto_approve", False))).lower(),
        "OPENAI_MODEL": getattr(trader.config, "openai_model", "gpt-5-mini"),
        "OPENAI_TIMEOUT_SECONDS": getattr(trader.config, "openai_timeout_seconds", 20.0),
        "AI_CANDIDATE_LIMIT": getattr(trader.config, "ai_candidate_limit", 5),
        "OPENAI_API_KEY": getattr(trader.config, "openai_api_key", ""),
        "SLACK_WEBHOOK_URL": getattr(trader.config, "slack_webhook_url", ""),
        "TELEGRAM_API_ID": getattr(trader.config, "telegram_api_id", "") or "",
        "TELEGRAM_API_HASH": getattr(trader.config, "telegram_api_hash", "") or "",
        "TELEGRAM_TARGET_CHANNELS": getattr(trader.config, "telegram_target_channels", "") or "",
    }
    value = runtime_values.get(key, "")
    return "" if value is None else str(value)


@app.get("/api/config")
def get_config():
    return {
        "trading_env": trader.TRADING_ENV,
        "dry_run": trader.DRY_RUN,
        "enable_live_trading": trader.ENABLE_LIVE_TRADING,
        "require_approval": trader.REQUIRE_APPROVAL,
        "order_submission_enabled": trader.ORDER_SUBMISSION_ENABLED,
        "real_orders_enabled": trader.REAL_ORDERS_ENABLED,
        "kistock_account": trader.config.kistock_account,
        "split_n": trader.SPLIT_N,
        "stop_loss_pct": trader.STOP_LOSS_PCT,
        "take_profit": trader.TAKE_PROFIT,
        "rsi_buy": trader.RSI_BUY,
        "rsi_sell": trader.RSI_SELL,
        "total_capital": trader.TOTAL_CAPITAL,
        "max_positions": trader.MAX_POSITIONS,
        "max_single_weight": trader.MAX_SINGLE_WEIGHT,
        "cash_buffer": trader.CASH_BUFFER,
        "max_daily_loss_pct": trader.MAX_DAILY_LOSS_PCT,
        "watchlist": trader.WATCHLIST,
        "scan_universe_size": trader.SCAN_UNIVERSE_SIZE,
        "kospi_universe_size": len(trader.KOSPI_UNIVERSE),
        "strategy_sources": [
            "RSI recovery + MACD confirmation",
            "Bollinger mean reversion",
            "Trend pullback with short RSI",
            "20-day breakout with volume",
            "FinRL-X inspired weight-centric allocation",
        ],
        "ai_analysis": _ai_analysis_config(),
    }




@app.get("/api/env")
def get_env_settings():
    env_path = _public_value("ENV_PATH", ENV_PATH)
    values = _read_env_values(env_path)
    fields = []
    for field in ENV_FIELDS:
        key = field["key"]
        text = ENV_FIELD_TEXT.get(key, {})
        value = _virtual_env_value(key, values) if field.get("virtual") else _current_env_field_value(key, values)
        item = {
            "key": key,
            "label": text.get("label", field["label"]),
            "type": field["type"],
            "options": field.get("options", []),
            "hint": text.get("hint", field.get("hint", "")),
            "secret": field["type"] == "secret",
            "virtual": bool(field.get("virtual")),
            "has_value": bool(value),
            "value": value,
            "masked": "",
        }
        fields.append(item)
    return {
        "path": str(env_path),
        "exists": env_path.exists(),
        "requires_restart": True,
        "fields": fields,
    }




@app.post("/api/env")
def update_env_settings(payload: dict = Body(...)):
    raw_updates = payload.get("values")
    if not isinstance(raw_updates, dict):
        raise HTTPException(status_code=400, detail="values must be an object")

    updates: dict[str, str] = {}
    for key, value in raw_updates.items():
        if key not in ENV_FIELD_MAP:
            raise HTTPException(status_code=400, detail=f"{key} is not editable")
        field = ENV_FIELD_MAP[key]
        if field["type"] == "secret" and str(value).strip() == "":
            continue
        updates[key] = _validate_env_value(key, value)

    if updates:
        updates = _expand_virtual_env_updates(updates)
        _write_env_values(updates, _public_value("ENV_PATH", ENV_PATH))
        _apply_runtime_env_updates(updates)
        _apply_strategy_env_updates(updates)
    return {
        "ok": True,
        "updated": sorted(updates.keys()),
        "requires_restart": False,
    }




@app.post("/api/circuit-breaker/reset")
def reset_circuit_breaker():
    KIStockAPI.reset_circuit()
    return {"ok": True, "circuit_breaker": KIStockAPI.circuit_status()}




@app.post("/api/auto-approval")
def set_auto_approval(payload: dict = Body(...)):
    enabled = bool(payload.get("enabled"))
    _save_auto_approval(enabled)
    processed = _auto_approve_pending_approvals() if enabled else []
    return {"ok": True, "enabled": enabled, "processed": processed, "processed_count": len(processed)}




@app.post("/api/runtime/order-mode")
def set_runtime_order_mode(payload: dict = Body(...)):
    key = str(payload.get("key", "")).strip()
    enabled = bool(payload.get("enabled"))
    updates = _runtime_order_mode_updates(key, enabled)
    _write_env_values(updates, _public_value("ENV_PATH", ENV_PATH))
    _apply_runtime_env_updates(updates)
    return {
        "ok": True,
        "updated": sorted(updates.keys()),
        "trading_env": trader.TRADING_ENV,
        "dry_run": trader.DRY_RUN,
        "enable_live_trading": trader.ENABLE_LIVE_TRADING,
        "order_submission_enabled": trader.ORDER_SUBMISSION_ENABLED,
        "real_orders_enabled": trader.REAL_ORDERS_ENABLED,
        "requires_restart": False,
    }
