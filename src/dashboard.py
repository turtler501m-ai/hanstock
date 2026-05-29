import json
import hashlib
import concurrent.futures
import os
import re
import socket
import sqlite3
import subprocess
import threading
import time
from pathlib import Path

from dotenv import load_dotenv
from fastapi import Body, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

load_dotenv()

from src import trader  # noqa: E402
from src.trader import KIStockAPI  # noqa: E402
from src.api.kis_api import KISAccountError, KISConfigError, KISRateLimitError  # noqa: E402
from src.api.quantconnect_api import QuantConnectAPI, QuantConnectCredentials  # noqa: E402
from src.futures_signals import (  # noqa: E402
    FuturesSignalParseError,
    FuturesSignalService,
    OhlcCandle,
    TelegramSignalCollector,
    collector_status,
)
from src.notifier.slack import slack_order as _slack_order, slack_error as _slack_error  # noqa: E402
from src.strategy.seven_split import adjust_tick_size  # noqa: E402


app = FastAPI(title="Seven Split Dashboard", version="1.0.0")

BASE_DIR = Path(__file__).resolve().parent.parent
WEB_DIR = BASE_DIR / "web"
DATA_DIR = BASE_DIR / "data"
DB_PATH = trader.DB_PATH
FINRL_DIR = BASE_DIR / "vendor" / "FinRL"
BALANCE_CACHE = trader.RUNTIME_DIR / "balance_snapshot.json"
CANDIDATE_CACHE = trader.RUNTIME_DIR / "candidate_snapshot.json"
AUTO_APPROVAL_STATE = trader.RUNTIME_DIR / "auto_approval.json"
QUANTCONNECT_MNQ_DIR = BASE_DIR / "src" / "integrations" / "quantconnect" / "mnq_paper_auto"
QUANTCONNECT_MNQ_RESULTS = trader.RUNTIME_DIR / "quantconnect_mnq_results.json"
QUANTCONNECT_AUTH_CACHE = trader.RUNTIME_DIR / "quantconnect_auth_cache.json"
QUANTCONNECT_CLOUD_CACHE = trader.RUNTIME_DIR / "quantconnect_cloud_cache.json"
ENV_PATH = BASE_DIR / ".env"
CANDIDATE_CACHE_TTL_SECONDS = int(os.environ.get("CANDIDATE_CACHE_TTL_SECONDS", "180"))
BALANCE_CACHE_TTL_SECONDS = int(os.environ.get("BALANCE_CACHE_TTL_SECONDS", "30"))
BALANCE_FETCH_TIMEOUT_SECONDS = float(os.environ.get("BALANCE_FETCH_TIMEOUT_SECONDS", "25"))
GIT_FETCH_TIMEOUT_SECONDS = float(os.environ.get("GIT_FETCH_TIMEOUT_SECONDS", "3"))
_balance_fetch_lock = threading.Lock()
ENV_FIELDS = [
    {"key": "KISTOCK_APP_KEY", "label": "KIS App Key", "type": "secret"},
    {"key": "KISTOCK_APP_SECRET", "label": "KIS App Secret", "type": "secret"},
    {"key": "KISTOCK_ACCOUNT", "label": "KIS Account", "type": "secret", "hint": "怨꾩쥖踰덊샇 8?먮━ ?먮뒗 怨꾩쥖踰덊샇 8?먮━ + ?곹뭹肄붾뱶 2?먮━, ?? 12345678 ?먮뒗 1234567801"},
    {"key": "TRADING_ENV", "label": "嫄곕옒?섍꼍", "type": "select", "options": ["demo", "real"], "hint": "demo=紐⑥쓽?ъ옄, real=?ㅼ쟾?ъ옄"},
    {"key": "DRY_RUN", "label": "二쇰Ц李⑤떒", "type": "bool", "hint": "true?대㈃ 二쇰Ц李⑤떒 ON ?곹깭濡?KIS 二쇰Ц API ?꾩넚??留됯퀬 湲곕줉留??④퉩?덈떎."},
    {"key": "ENABLE_LIVE_TRADING", "label": "?ㅼ쟾留ㅻℓ 理쒖쥌?덉슜", "type": "bool", "hint": "?ㅼ쟾二쇰Ц???덉슜?섎뒗 理쒖쥌 ?덉쟾 ?ㅼ쐞移섏엯?덈떎."},
    {"key": "REQUIRE_APPROVAL", "label": "二쇰Ц?뱀씤 ?꾩슂", "type": "bool"},
    {"key": "SPLIT_N", "label": "Split N", "type": "int"},
    {"key": "STOP_LOSS_PCT", "label": "Stop Loss %", "type": "float"},
    {"key": "TAKE_PROFIT", "label": "Take Profit %", "type": "float"},
    {"key": "RSI_BUY", "label": "RSI Buy", "type": "int"},
    {"key": "RSI_SELL", "label": "RSI Sell", "type": "int"},
    {"key": "TOTAL_CAPITAL", "label": "Total Capital", "type": "float"},
    {"key": "MAX_POSITIONS", "label": "Max Positions", "type": "int"},
    {"key": "MAX_SINGLE_WEIGHT", "label": "Max Single Weight", "type": "float"},
    {"key": "CASH_BUFFER", "label": "Cash Buffer", "type": "float"},
    {"key": "MAX_DAILY_LOSS_PCT", "label": "Max Daily Loss %", "type": "float"},
    {"key": "SCAN_UNIVERSE_SIZE", "label": "Scan Universe Size", "type": "int"},
    {"key": "KIS_CIRCUIT_COOLDOWN_SECONDS", "label": "KIS API 李⑤떒 ?湲곗큹", "type": "int", "hint": "KIS API ?ㅻ쪟 ???ъ떆?꾧퉴吏 湲곕떎由??쒓컙(珥??낅땲?? ??????쒕쾭 ?ъ떆?????곸슜?⑸땲??"},
    {"key": "TRADE_DB_PATH", "label": "Trade DB Path", "type": "text"},
    {"key": "ACTIVE_MODEL_VERSION", "label": "Active Model Version", "type": "text"},
    {"key": "AI_STRATEGY_ENABLED", "label": "AI Strategy Enabled", "type": "bool"},
    {"key": "AI_SCORE_WEIGHT", "label": "AI Score Weight", "type": "float"},
    {"key": "AI_MIN_MODEL_CONFIDENCE", "label": "AI Min Confidence", "type": "float"},
    {"key": "AI_REQUIRE_BACKTEST_PASS", "label": "AI Require Backtest Pass", "type": "bool"},
    {"key": "AI_AUTO_APPROVE", "label": "AI Auto Approve", "type": "bool"},
    {"key": "OPENAI_API_KEY", "label": "OpenAI API Key", "type": "secret"},
    {"key": "OPENAI_MODEL", "label": "OpenAI Model", "type": "text"},
    {"key": "OPENAI_TIMEOUT_SECONDS", "label": "OpenAI Timeout Seconds", "type": "float"},
    {"key": "AI_CANDIDATE_LIMIT", "label": "AI Candidate Limit", "type": "int"},
    {"key": "SLACK_WEBHOOK_URL", "label": "Slack Webhook URL", "type": "secret"},
    {"key": "TELEGRAM_API_ID", "label": "Telegram API ID", "type": "secret"},
    {"key": "TELEGRAM_API_HASH", "label": "Telegram API Hash", "type": "secret"},
    {"key": "TELEGRAM_SESSION_NAME", "label": "Telegram Session Name", "type": "text", "hint": "Local Telethon session path. Keep it out of git."},
    {"key": "TELEGRAM_TARGET_CHANNELS", "label": "Telegram Target Channels", "type": "text", "hint": "Comma-separated channel usernames, IDs, or invite targets."},
]
ENV_FIELD_MAP = {field["key"]: field for field in ENV_FIELDS}
VENDOR_PROJECTS = {
    "finrl": {
        "name": "FinRL",
        "path": BASE_DIR / "vendor" / "FinRL",
        "package": "finrl",
        "dashboard": "/finrl",
        "license_hint": "MIT",
        "adapter": "Weight-centric allocation for current KIS holdings",
        "entrypoints": [
            "finrl/train.py",
            "finrl/test.py",
            "finrl/trade.py",
            "finrl/meta/env_stock_trading/env_stocktrading.py",
            "finrl/agents/stablebaselines3/models.py",
        ],
    },
    "qlib": {
        "name": "Qlib",
        "path": BASE_DIR / "vendor" / "qlib",
        "package": "qlib",
        "dashboard": "/vendors",
        "license_hint": "MIT",
        "adapter": "AI quant research pipeline map: dataset, feature, model, signal, execution",
        "entrypoints": [
            "qlib/workflow",
            "qlib/model",
            "qlib/contrib",
            "qlib/backtest",
            "examples",
        ],
    },
    "pyportfolioopt": {
        "name": "PyPortfolioOpt",
        "path": BASE_DIR / "vendor" / "PyPortfolioOpt",
        "package": "pypfopt",
        "dashboard": "/vendors",
        "license_hint": "MIT",
        "adapter": "Portfolio target weights and risk-aware rebalance planning",
        "entrypoints": [
            "pypfopt/efficient_frontier",
            "pypfopt/risk_models",
            "pypfopt/expected_returns",
            "pypfopt/objective_functions",
        ],
    },
    "freqtrade": {
        "name": "freqtrade",
        "path": BASE_DIR / "vendor" / "freqtrade",
        "package": "freqtrade",
        "dashboard": "/vendors",
        "license_hint": "GPL-3.0",
        "adapter": "Dry-run, approval workflow, strategy status concepts only; source kept isolated",
        "entrypoints": [
            "freqtrade/strategy",
            "freqtrade/rpc",
            "freqtrade/persistence",
            "freqtrade/freqai",
            "user_data/strategies",
        ],
    },
}

app.mount("/static", StaticFiles(directory=WEB_DIR / "static"), name="static")
app.mount("/templates", StaticFiles(directory=WEB_DIR / "templates"), name="templates")


def _required_env_missing() -> list[str]:
    required = ["KISTOCK_APP_KEY", "KISTOCK_APP_SECRET", "KISTOCK_ACCOUNT"]
    missing = [name for name in required if not os.environ.get(name)]
    if _account_format_warning(trader.config.kistock_account):
        missing.append("KISTOCK_ACCOUNT_FORMAT")
    return missing


def _account_format_warning(account: str) -> str:
    digits = "".join(char for char in str(account or "") if char.isdigit())
    if not digits:
        return "KISTOCK_ACCOUNT is required"
    if len(digits) not in {8, 10}:
        return "KISTOCK_ACCOUNT must be 8 digits, or 10 digits including 2-digit product code"
    return ""


def _to_int(value, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _to_float(value, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _summary_item(summary):
    if isinstance(summary, list):
        return summary[0] if summary else {}
    if isinstance(summary, dict):
        return summary
    return {}


def _clamp_ratio(value: float) -> float:
    return max(0.0, min(1.0, value))


def _holding_value(stock: dict, qty: int, price: int) -> int:
    broker_value = _to_int(stock.get("evlu_amt"))
    if broker_value > 0:
        return broker_value
    return qty * price


def _portfolio_totals(cash: int, summary_total: int, holdings: list[dict]) -> dict:
    stock_eval = sum(_to_int(holding.get("value")) for holding in holdings)
    broker_total = max(0, summary_total)
    calculated_total = max(0, cash) + stock_eval
    effective_total = broker_total if broker_total >= stock_eval else calculated_total
    if effective_total <= 0:
        effective_total = calculated_total
    return {
        "stock_eval": stock_eval,
        "broker_total_eval": broker_total,
        "calculated_total_eval": calculated_total,
        "total_eval": effective_total,
        "cash_ratio": _clamp_ratio(cash / effective_total) if effective_total > 0 else 0.0,
        "stock_ratio": _clamp_ratio(stock_eval / effective_total) if effective_total > 0 else 0.0,
    }


def _parse_balance(balance_data: dict) -> dict:
    if balance_data.get("_error"):
        raise RuntimeError(balance_data["_error"])

    stocks = balance_data.get("output1", [])
    first_summary = _summary_item(balance_data.get("output2", [{}]))

    holdings = []
    for stock in stocks:
        qty = _to_int(stock.get("hldg_qty"))
        price = _to_int(stock.get("prpr"))
        value = _holding_value(stock, qty, price)
        if price <= 0 and qty > 0:
            price = round(value / qty)
        holdings.append({
            "symbol": stock.get("pdno", ""),
            "name": stock.get("prdt_name", stock.get("pdno", "")),
            "qty": qty,
            "price": price,
            "rt": _to_float(stock.get("evlu_pfls_rt")),
            "pnl": _to_int(stock.get("evlu_pfls_amt")),
            "value": value,
            "_raw": stock,
        })

    summary_total = _to_int(first_summary.get("tot_evlu_amt"))
    summary_stock_eval = _to_int(first_summary.get("scts_evlu_amt"))
    cash = _to_int(first_summary.get("prvs_rcdl_excc_amt"))
    if cash <= 0 and summary_total > 0 and summary_stock_eval > 0:
        cash = max(0, summary_total - summary_stock_eval)
    if cash <= 0:
        cash = _to_int(first_summary.get("dnca_tot_amt"))
    totals = _portfolio_totals(cash, summary_total, holdings)
    return {
        "cash": cash,
        "total_eval": totals["total_eval"],
        "broker_total_eval": totals["broker_total_eval"],
        "calculated_total_eval": totals["calculated_total_eval"],
        "stock_eval": totals["stock_eval"],
        "cash_ratio": totals["cash_ratio"],
        "stock_ratio": totals["stock_ratio"],
        "pnl": _to_int(first_summary.get("evlu_pfls_smtl_amt")),
        "holdings": holdings,
    }


def _get_api() -> KIStockAPI:
    return KIStockAPI(notify_errors=False)


def _account_cache_key() -> str:
    source = f"{trader.TRADING_ENV}:{trader.config.kistock_account}"
    return hashlib.sha256(source.encode("utf-8")).hexdigest()


def _save_balance_cache(balance_data: dict) -> None:
    BALANCE_CACHE.parent.mkdir(parents=True, exist_ok=True)
    BALANCE_CACHE.write_text(
        json.dumps({
            "cached_at": trader.datetime.now(trader.KST).isoformat(),
            "trading_env": trader.TRADING_ENV,
            "account_key": _account_cache_key(),
            "data": balance_data,
        }, ensure_ascii=False),
        encoding="utf-8",
    )


def _clear_balance_cache() -> None:
    try:
        BALANCE_CACHE.unlink(missing_ok=True)
    except Exception:
        pass


def _load_balance_cache() -> dict | None:
    if not BALANCE_CACHE.exists():
        return None
    try:
        cached = json.loads(BALANCE_CACHE.read_text(encoding="utf-8"))
    except Exception:
        return None
    if cached.get("trading_env") != trader.TRADING_ENV:
        return None
    if cached.get("account_key") != _account_cache_key():
        return None
    data = cached.get("data")
    if not isinstance(data, dict):
        return None
    data["_cache"] = {"stale": True, "cached_at": cached.get("cached_at", "")}
    return data


def _balance_cache_age_seconds(balance_data: dict) -> float | None:
    cached_at = balance_data.get("_cache", {}).get("cached_at", "")
    if not cached_at:
        return None
    try:
        return (trader.datetime.now(trader.KST) - trader.datetime.fromisoformat(cached_at)).total_seconds()
    except Exception:
        return None


def _run_with_timeout(func, timeout_seconds: float):
    executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    future = executor.submit(func)
    try:
        return future.result(timeout=timeout_seconds)
    finally:
        executor.shutdown(wait=False, cancel_futures=True)


def _get_balance_data(api: KIStockAPI, allow_cache: bool = True) -> dict:
    cached = _load_balance_cache() if allow_cache else None
    if allow_cache:
        if cached is not None:
            age = _balance_cache_age_seconds(cached)
            if age is not None and age < BALANCE_CACHE_TTL_SECONDS:
                return cached

    with _balance_fetch_lock:
        if allow_cache:
            cached = _load_balance_cache()
            if cached is not None:
                age = _balance_cache_age_seconds(cached)
                if age is not None and age < BALANCE_CACHE_TTL_SECONDS:
                    return cached
        try:
            balance_data = _run_with_timeout(api.get_balance, BALANCE_FETCH_TIMEOUT_SECONDS)
        except concurrent.futures.TimeoutError:
            if cached is not None:
                return cached
            raise RuntimeError("KIS balance API timed out")
        except KISConfigError:
            if allow_cache:
                cached = _load_balance_cache()
                if cached is not None:
                    return cached
            raise
        except Exception:
            if allow_cache:
                cached = _load_balance_cache()
                if cached is not None:
                    return cached
            raise
        try:
            _parse_balance(balance_data)
        except Exception:
            if allow_cache:
                cached = _load_balance_cache()
                if cached is not None:
                    return cached
            raise
        _save_balance_cache(balance_data)
        return balance_data


def _load_candidate_cache(
    min_score: int,
    ranker: str = "gpt_5_mini",
    optimizer: str = "score_tilted_inverse_vol",
) -> dict | None:
    if not CANDIDATE_CACHE.exists():
        return None
    try:
        cached = json.loads(CANDIDATE_CACHE.read_text(encoding="utf-8"))
    except Exception:
        return None
    expected_ai_signature = {
        "enabled": bool(getattr(trader.config, "ai_strategy_enabled", False)),
        "model": getattr(trader.config, "openai_model", "gpt-5-mini"),
        "candidate_limit": int(getattr(trader.config, "ai_candidate_limit", 5) or 5),
        "api_configured": bool(str(getattr(trader.config, "openai_api_key", "") or "").strip()),
    }
    if (
        cached.get("trading_env") != trader.TRADING_ENV
        or cached.get("min_score") != min_score
        or cached.get("ranker") != ranker
        or cached.get("optimizer") != optimizer
        or cached.get("ai_signature") != expected_ai_signature
    ):
        return None
    cached_at = cached.get("cached_at")
    if not cached_at:
        return None
    try:
        age = (trader.datetime.now(trader.KST) - trader.datetime.fromisoformat(cached_at)).total_seconds()
    except ValueError:
        return None
    if age > CANDIDATE_CACHE_TTL_SECONDS:
        return None
    rows = cached.get("rows")
    if not isinstance(rows, list):
        return None
    return {
        "candidates": rows,
        "scan_summary": cached.get("scan_summary", []),
        "scanned": cached.get("scanned", len(rows)),
        "min_score": min_score,
        "_cache": {"stale": False, "cached_at": cached_at},
    }


def _save_candidate_cache(
    min_score: int,
    rows: list[dict],
    scan_summary: list[dict],
    scanned: int,
    ranker: str = "gpt_5_mini",
    optimizer: str = "score_tilted_inverse_vol",
) -> None:
    CANDIDATE_CACHE.parent.mkdir(parents=True, exist_ok=True)
    CANDIDATE_CACHE.write_text(
        json.dumps({
            "cached_at": trader.datetime.now(trader.KST).isoformat(),
            "trading_env": trader.TRADING_ENV,
            "min_score": min_score,
            "ranker": ranker,
            "optimizer": optimizer,
            "ai_signature": {
                "enabled": bool(getattr(trader.config, "ai_strategy_enabled", False)),
                "model": getattr(trader.config, "openai_model", "gpt-5-mini"),
                "candidate_limit": int(getattr(trader.config, "ai_candidate_limit", 5) or 5),
                "api_configured": bool(str(getattr(trader.config, "openai_api_key", "") or "").strip()),
            },
            "rows": rows,
            "scan_summary": scan_summary,
            "scanned": scanned,
        }, ensure_ascii=False),
        encoding="utf-8",
    )


def build_dashboard_signals(api, parsed: dict) -> list[dict]:
    signals = []
    for holding in parsed["holdings"]:
        daily = api.get_daily(holding["symbol"], n=60)
        signal = trader.generate_signal(holding["_raw"], daily)
        indicators = signal.get("indicators", {})
        signals.append({
            "symbol": holding["symbol"],
            "name": holding["name"],
            "qty": holding["qty"],
            "price": holding["price"],
            "rt": holding["rt"],
            "action": signal.get("action", "hold"),
            "signal_qty": signal.get("qty", 0),
            "signal_price": signal.get("price", 0),
            "reason": signal.get("reason", ""),
            "rsi": indicators.get("rsi"),
            "rsi2": indicators.get("rsi2"),
            "sma20": indicators.get("sma20"),
            "sma60": indicators.get("sma60"),
            "bb_lo": indicators.get("bb_lo"),
            "bb_hi": indicators.get("bb_hi"),
            "strategy_score": indicators.get("strategy_score"),
            "macd_hist": indicators.get("macd_hist"),
        })
    return signals


def build_dashboard_candidates(
    api,
    parsed: dict,
    min_score: int = 2,
    ranker: str = "gpt_5_mini",
    ranker_weight: float = 0.4,
    optimizer: str = "score_tilted_inverse_vol",
) -> dict:
    held_symbols = {holding["symbol"] for holding in parsed["holdings"]}
    universe = trader.build_scan_universe(api, held_symbols)
    
    if ranker == "gpt_5_mini" and ranker_weight == 0.4:
        scan_result = trader.find_candidates(held_symbols, universe=universe, min_score=min_score)
    else:
        ranker_param = "rule_only" if ranker == "none" else ranker
        orig_weight = trader.config.ai_score_weight
        orig_model = trader.config.openai_model
        orig_enabled = trader.config.ai_strategy_enabled
        try:
            trader.config.ai_score_weight = ranker_weight
            trader.config.openai_model = ranker_param
            if ranker_param == "rule_only":
                trader.config.ai_strategy_enabled = False
            else:
                trader.config.ai_strategy_enabled = True
                
            scan_result = trader.find_candidates(held_symbols, universe=universe, min_score=min_score, ranker=ranker_param)
        finally:
            trader.config.ai_score_weight = orig_weight
            trader.config.openai_model = orig_model
            trader.config.ai_strategy_enabled = orig_enabled
        
    candidates = scan_result.get("candidates", [])
    
    if optimizer == "score_tilted_inverse_vol":
        orders = trader.build_orders(candidates, api.get_quote, len(parsed["holdings"]), parsed["cash"])
    else:
        orders = trader.build_orders(
            candidates, api.get_quote, len(parsed["holdings"]), parsed["cash"], optimizer=optimizer
        )
        
    order_by_ticker = {order["ticker"]: order for order in orders}

    rows = []
    for candidate in candidates:
        order = order_by_ticker.get(candidate["ticker"], {})
        row = {
            "ticker": candidate["ticker"],
            "name": candidate.get("name", candidate["ticker"]),
            "current_price": candidate["current_price"],
            "score": candidate["score"],
            "reasons": candidate["reasons"],
            "rsi": candidate.get("rsi"),
            "rsi2": candidate.get("rsi2"),
            "macd_hist": candidate.get("macd_hist"),
            "sma20": candidate.get("sma20"),
            "sma60": candidate.get("sma60"),
            "bb_lo": candidate.get("bb_lo"),
            "bb_hi": candidate.get("bb_hi"),
            "planned_qty": order.get("quantity", 0),
            "limit_price": order.get("limit_price", 0),
            "estimated_cost": order.get("estimated_cost", 0),
            "universe_size": len(universe),
        }
        for key in (
            "rule_score",
            "ml_score",
            "final_score",
            "ai_enabled",
            "ai_model_status",
            "ai_model_version",
            "feature_version",
            "ai_score_weight",
            "ai_fallback_reason",
            "top_features",
        ):
            if key in candidate:
                row[key] = candidate[key]
        rows.append(row)

    return {
        "candidates": rows,
        "universe_size": len(universe),
        "scanned": scan_result.get("scanned", 0),
        "min_score": min_score,
        "scan_summary": scan_result.get("scan_summary", []),
        "scan_error": scan_result.get("scan_error"),
    }


def _build_candidate_orders_from_scan(candidates: list, *, held_count: int = 0, cash: int) -> list:
    """Build candidate orders using scan prices (no live quote lookup)."""
    available_slots = max(0, trader.MAX_POSITIONS - held_count)
    orders = []
    remaining_cash = cash
    for cand in candidates[:available_slots]:
        price = int(cand.get("current_price", 0) or 0)
        if price <= 0:
            continue
        limit_price = adjust_tick_size(price)
        if limit_price <= 0:
            continue
        qty = remaining_cash // limit_price
        if qty <= 0:
            continue
        estimated_cost = qty * limit_price
        orders.append({
            "ticker": cand["ticker"],
            "limit_price": limit_price,
            "quantity": qty,
            "estimated_cost": estimated_cost,
        })
        remaining_cash -= estimated_cost
    return orders


def build_dashboard_execution_plan() -> dict:
    api = _get_api()
    balance_data = _get_balance_data(api)
    parsed = _parse_balance(balance_data)
    runtime_bundle = trader.build_runtime_plan(api, balance_data)
    return {
        "mode": "dashboard",
        "plan": runtime_bundle["plan"],
        "cash": parsed["cash"],
        "remaining_cash": runtime_bundle["remaining_cash"],
        "total_eval": parsed["total_eval"],
        "pnl": parsed["pnl"],
        "daily_loss_halt": runtime_bundle["daily_loss_halt"],
        "scanned": runtime_bundle["candidate_scan"]["scanned"],
        "scan_error": runtime_bundle["candidate_scan"]["scan_error"],
    }


def _init_approval_db() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with trader.connect_db() as conn:
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


def _approval_row(row) -> dict:
    return dict(row)


def _approval_by_id(approval_id: int) -> dict | None:
    _init_approval_db()
    with trader.connect_db() as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM approvals WHERE id = ?", (approval_id,)).fetchone()
    return _approval_row(row) if row else None


def _auto_approval_enabled() -> bool:
    try:
        from src.db.repository import load_auto_approval_state
        return load_auto_approval_state()
    except Exception:
        if not AUTO_APPROVAL_STATE.exists():
            return False
        try:
            state = json.loads(AUTO_APPROVAL_STATE.read_text(encoding="utf-8"))
            return bool(state.get("enabled"))
        except Exception:
            return False


def _save_auto_approval(enabled: bool) -> None:
    try:
        AUTO_APPROVAL_STATE.parent.mkdir(parents=True, exist_ok=True)
        AUTO_APPROVAL_STATE.write_text(
            json.dumps({
                "enabled": bool(enabled),
                "updated_at": trader.datetime.now(trader.KST).isoformat(),
            }, ensure_ascii=False),
            encoding="utf-8",
        )
    except Exception:
        pass
        
    try:
        from src.db.repository import save_auto_approval_state
        save_auto_approval_state(enabled)
    except Exception:
        pass


def _read_env_values(path: Path = ENV_PATH) -> dict[str, str]:
    if not path.exists():
        return {}
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip()
        value = _env_value_without_inline_comment(value.strip())
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        values[key] = value
    return values


def _env_value_without_inline_comment(value: str) -> str:
    quote = None
    for index, char in enumerate(value):
        if char in ("'", '"') and (index == 0 or value[index - 1] != "\\"):
            quote = None if quote == char else (char if quote is None else quote)
        if char == "#" and quote is None and index > 0 and value[index - 1].isspace():
            return value[:index].strip()
    return value.strip()


def _mask_env_value(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 4:
        return "*" * len(value)
    return f"{value[:2]}{'*' * max(4, len(value) - 4)}{value[-2:]}"


def _validate_env_value(key: str, value: object) -> str:
    field = ENV_FIELD_MAP[key]
    value_text = _env_value_without_inline_comment(str(value).strip())
    field_type = field["type"]
    if field_type == "bool":
        lowered = value_text.lower()
        if lowered not in {"true", "false", "1", "0", "yes", "no", "on", "off"}:
            raise HTTPException(status_code=400, detail=f"{key} must be a boolean")
        return "true" if lowered in {"true", "1", "yes", "on"} else "false"
    if field_type == "int":
        try:
            int(value_text)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=f"{key} must be an integer") from exc
        return value_text
    if field_type == "float":
        try:
            float(value_text)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=f"{key} must be a number") from exc
        return value_text
    if field_type == "select":
        options = field.get("options", [])
        if value_text not in options:
            raise HTTPException(status_code=400, detail=f"{key} must be one of: {', '.join(options)}")
        return value_text
    if key == "KISTOCK_ACCOUNT":
        digits = "".join(char for char in value_text if char.isdigit())
        warning = _account_format_warning(digits)
        if warning:
            raise HTTPException(status_code=400, detail=warning)
        return digits
    return value_text


def _env_bool_value(values: dict[str, str], key: str, default: bool = False) -> bool:
    raw = str(values.get(key, str(default))).strip().lower()
    return raw in {"true", "1", "yes", "on"}


def _virtual_env_value(key: str, values: dict[str, str]) -> str:
    dry_run = _env_bool_value(values, "DRY_RUN", True)
    trading_env = values.get("TRADING_ENV", "demo")
    enable_live = _env_bool_value(values, "ENABLE_LIVE_TRADING", False)
    if key == "ORDER_SUBMISSION_ENABLED":
        return "true" if (not dry_run and (trading_env == "demo" or enable_live)) else "false"
    return ""


def _expand_virtual_env_updates(updates: dict[str, str]) -> dict[str, str]:
    expanded = dict(updates)
    order_submission = expanded.pop("ORDER_SUBMISSION_ENABLED", None)

    if order_submission is not None:
        expanded["DRY_RUN"] = "false" if _env_bool_value({"value": order_submission}, "value") else "true"

    return expanded


def _apply_runtime_env_updates(updates: dict[str, str]) -> None:
    for key, value in updates.items():
        if key == "TRADING_ENV":
            trader.config.trading_env = value
            trader.TRADING_ENV = value
        elif key == "DRY_RUN":
            parsed = _env_bool_value({"value": value}, "value")
            trader.config.dry_run = parsed
            trader.DRY_RUN = parsed
        elif key == "ENABLE_LIVE_TRADING":
            parsed = _env_bool_value({"value": value}, "value")
            trader.config.enable_live_trading = parsed
            trader.ENABLE_LIVE_TRADING = parsed

    trader.REAL_ORDERS_ENABLED = (
        (not trader.DRY_RUN)
        and trader.TRADING_ENV == "real"
        and trader.ENABLE_LIVE_TRADING
    )
    trader.ORDER_SUBMISSION_ENABLED = (
        (not trader.DRY_RUN)
        and (trader.TRADING_ENV == "demo" or trader.REAL_ORDERS_ENABLED)
    )


STRATEGY_ENV_BINDINGS = {
    "SPLIT_N": ("split_n", "SPLIT_N", int),
    "STOP_LOSS_PCT": ("stop_loss_pct", "STOP_LOSS_PCT", float),
    "TAKE_PROFIT": ("take_profit", "TAKE_PROFIT", float),
    "RSI_BUY": ("rsi_buy", "RSI_BUY", int),
    "RSI_SELL": ("rsi_sell", "RSI_SELL", int),
    "TOTAL_CAPITAL": ("total_capital", "TOTAL_CAPITAL", float),
    "MAX_POSITIONS": ("max_positions", "MAX_POSITIONS", int),
    "MAX_SINGLE_WEIGHT": ("max_single_weight", "MAX_SINGLE_WEIGHT", float),
    "CASH_BUFFER": ("cash_buffer", "CASH_BUFFER", float),
    "MAX_DAILY_LOSS_PCT": ("max_daily_loss_pct", "MAX_DAILY_LOSS_PCT", float),
    "SCAN_UNIVERSE_SIZE": ("scan_universe_size", "SCAN_UNIVERSE_SIZE", int),
}


AI_ENV_BINDINGS = {
    "AI_STRATEGY_ENABLED": ("ai_strategy_enabled", lambda value: str(value).lower() in ("1", "true", "yes", "on")),
    "AI_SCORE_WEIGHT": ("ai_score_weight", float),
    "AI_MIN_MODEL_CONFIDENCE": ("ai_min_model_confidence", float),
    "AI_REQUIRE_BACKTEST_PASS": ("ai_require_backtest_pass", lambda value: str(value).lower() in ("1", "true", "yes", "on")),
    "AI_AUTO_APPROVE": ("ai_auto_approve", lambda value: str(value).lower() in ("1", "true", "yes", "on")),
    "OPENAI_API_KEY": ("openai_api_key", str),
    "OPENAI_MODEL": ("openai_model", str),
    "OPENAI_TIMEOUT_SECONDS": ("openai_timeout_seconds", float),
    "AI_CANDIDATE_LIMIT": ("ai_candidate_limit", int),
}


def _apply_strategy_env_updates(updates: dict[str, str]) -> None:
    for key, value in updates.items():
        binding = STRATEGY_ENV_BINDINGS.get(key)
        if binding:
            config_attr, trader_attr, caster = binding
            parsed = caster(value)
            setattr(trader.config, config_attr, parsed)
            setattr(trader, trader_attr, parsed)
            continue
        ai_binding = AI_ENV_BINDINGS.get(key)
        if ai_binding:
            config_attr, caster = ai_binding
            setattr(trader.config, config_attr, caster(value))


def _ai_analysis_config() -> dict:
    model_name = getattr(trader.config, "openai_model", "gpt-5-mini")
    api_key = str(getattr(trader.config, "openai_api_key", "") or "").strip()
    ai_enabled = bool(getattr(trader.config, "ai_strategy_enabled", False))
    score_weight = max(0.0, min(1.0, float(getattr(trader.config, "ai_score_weight", 0.0) or 0.0)))
    candidate_limit = int(getattr(trader.config, "ai_candidate_limit", 5) or 5)
    return {
        "enabled": ai_enabled,
        "provider": "openai_responses",
        "provider_label": "OpenAI Responses API",
        "model_name": model_name,
        "model_type": "OpenAI text model",
        "model_available": bool(api_key),
        "account_priority": "current_kis_account",
        "account": trader.config.kistock_account,
        "account_label": "현재 KIS 계좌 1순위",
        "openai_account_priority": "openai_api_first",
        "openai_api_configured": bool(api_key),
        "score_weight": score_weight if ai_enabled else 0.0,
        "rule_weight": 1.0 - score_weight if ai_enabled else 1.0,
        "min_confidence": float(getattr(trader.config, "ai_min_model_confidence", 0.6) or 0.6),
        "candidate_limit": candidate_limit,
        "auto_approve": bool(getattr(trader.config, "ai_auto_approve", False)),
        "require_backtest_pass": bool(getattr(trader.config, "ai_require_backtest_pass", True)),
        "fallback_mode": "rule_based" if (not ai_enabled or not api_key) else "",
        "flow": [
            "현재 KIS 계좌의 보유/현금/리스크 상태를 1순위 기준으로 읽습니다.",
            "관심종목과 거래량 상위 종목의 RSI, MACD, Bollinger, 추세, 거래량 피처를 계산합니다.",
            f"AI가 켜져 있고 OPENAI_API_KEY가 있으면 OpenAI Responses API로 상위 {candidate_limit}개 후보만 우선 평가합니다.",
            "최종 점수는 룰 점수와 AI 점수를 AI_SCORE_WEIGHT 비율로 결합합니다.",
            "주문은 승인 대기열과 DRY_RUN/실거래 보호 설정을 통과해야만 처리됩니다.",
        ],
    }



def _runtime_order_mode_updates(key: str, enabled: bool) -> dict[str, str]:
    normalized = key.upper()
    if normalized == "DRY_RUN":
        return {"DRY_RUN": "true" if enabled else "false"}
    raise HTTPException(status_code=400, detail="key must be DRY_RUN")


def _serialize_env_value(value: str) -> str:
    if not value or any(char.isspace() for char in value) or "#" in value:
        return json.dumps(value, ensure_ascii=False)
    return value


def _write_env_values(updates: dict[str, str], path: Path = ENV_PATH) -> None:
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    seen: set[str] = set()
    output: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            output.append(line)
            continue
        key = stripped.split("=", 1)[0].strip()
        if key in updates:
            value_part = line.split("=", 1)[1]
            suffix = ""
            comment_index = value_part.find(" #")
            if comment_index >= 0:
                suffix = value_part[comment_index:]
            output.append(f"{key}={_serialize_env_value(updates[key])}{suffix}")
            seen.add(key)
        else:
            output.append(line)
    missing = [key for key in updates if key not in seen]
    if missing:
        if output and output[-1].strip():
            output.append("")
        output.append("# Dashboard updates")
        output.extend(f"{key}={_serialize_env_value(updates[key])}" for key in missing)
    path.write_text("\n".join(output) + "\n", encoding="utf-8")


@app.get("/", response_class=FileResponse)
def read_root():
    return FileResponse(WEB_DIR / "templates" / "index.html")


@app.get("/finrl", response_class=FileResponse)
def read_finrl_dashboard():
    return FileResponse(WEB_DIR / "templates" / "finrl.html")


@app.get("/vendors", response_class=FileResponse)
def read_vendor_dashboard():
    return FileResponse(WEB_DIR / "templates" / "vendors.html")


@app.get("/ai-dashboard", response_class=FileResponse)
def read_ai_dashboard():
    return FileResponse(WEB_DIR / "templates" / "ai_dashboard.html")


@app.get("/ai-dashboard/futures-signals", response_class=FileResponse)
def read_futures_signals_dashboard():
    return FileResponse(WEB_DIR / "templates" / "futures_signals.html")


@app.get("/env-settings", response_class=FileResponse)
def read_env_settings():
    return FileResponse(WEB_DIR / "templates" / "env_settings.html")


_FUTURES_SIGNAL_SERVICE: FuturesSignalService | None = None


def _is_poll_running() -> bool:
    """poll.py 프로세스가 실행 중인지 확인"""
    try:
        import psutil
        for proc in psutil.process_iter(['cmdline']):
            cmdline = proc.info.get('cmdline') or []
            if any('poll.py' in str(c) for c in cmdline):
                return True
        return False
    except Exception:
        # psutil 없으면 상태 파일로 확인
        state_file = Path(".runtime/poll_running")
        return state_file.exists()


def _get_futures_signal_service() -> FuturesSignalService:
    global _FUTURES_SIGNAL_SERVICE
    if _FUTURES_SIGNAL_SERVICE is None:
        service = FuturesSignalService()
        _seed_futures_signal_service(service)
        _FUTURES_SIGNAL_SERVICE = service
    return _FUTURES_SIGNAL_SERVICE


def _seed_futures_signal_service(service: FuturesSignalService) -> None:
    seed_rows = [
        (
            "tg-sample-001",
            "2026-05-05T09:15:00+09:00",
            "#MNQ M26 LONG\nEntry: 18325.25\nSL 18280\nTP1 18370\nTP2 18420",
            [
                OhlcCandle("2026-05-05T09:16:00+09:00", open=18325.25, high=18362, low=18305, close=18355),
                OhlcCandle("2026-05-05T09:17:00+09:00", open=18355, high=18372, low=18343, close=18368),
            ],
        ),
        (
            "tg-sample-002",
            "2026-05-05T10:05:00+09:00",
            "MCL M26 SELL\nEntry: 64.82\nSL 65.18\nTP1 64.35\nTP2 63.95",
            [
                OhlcCandle("2026-05-05T10:06:00+09:00", open=64.82, high=65.2, low=64.32, close=64.7),
            ],
        ),
        (
            "tg-sample-003",
            "2026-05-05T10:40:00+09:00",
            "GC Q26 LONG\nEntry: 2358.4\nSL 2350\nTP1 2371",
            [
                OhlcCandle("2026-05-05T10:41:00+09:00", open=2358.4, high=2362, low=2349.8, close=2351),
            ],
        ),
    ]
    for message_id, received_at, text, candles in seed_rows:
        record = service.ingest_message(
            text,
            source="telegram_sample",
            source_message_id=message_id,
            received_at=trader.datetime.fromisoformat(received_at),
        )
        service.verify(record.signal.id, candles)


def _futures_signal_public_id(record) -> str:
    return record.signal.source_message_id or record.signal.id


def _futures_signal_confidence(record) -> float:
    if record.verification is None:
        return 0.68
    if record.verification.status == "verified":
        return 0.88
    if record.verification.requires_manual_review:
        return 0.74
    if record.verification.status == "rejected":
        return 0.61
    return 0.7


def _futures_risk_reward(record) -> float | None:
    signal = record.signal
    if not signal.take_profits:
        return None
    risk = abs(signal.entry - signal.stop_loss)
    if risk <= 0:
        return None
    reward = abs(signal.take_profits[0] - signal.entry)
    return round(reward / risk, 2)


def _futures_signal_record_to_api(record) -> dict:
    signal = record.signal
    verification = record.verification
    status = verification.status if verification else signal.status
    return {
        "id": _futures_signal_public_id(record),
        "internal_id": signal.id,
        "received_at": signal.received_at.isoformat() if signal.received_at else None,
        "source": signal.source,
        "channel": "overseas-futures-signals",
        "symbol": signal.symbol,
        "market": _futures_market_name(signal.symbol),
        "side": "buy" if signal.direction == "long" else "sell",
        "direction": signal.direction,
        "entry": signal.entry,
        "entry_price": signal.entry,
        "stop": signal.stop_loss,
        "stop_loss": signal.stop_loss,
        "targets": list(signal.take_profits),
        "take_profit_1": signal.take_profits[0] if signal.take_profits else None,
        "confidence": _futures_signal_confidence(record),
        "parse_status": signal.status,
        "status": status,
        "verification_status": status,
        "verification": {
            "status": status,
            "outcome": verification.outcome if verification else "pending",
            "hit_at": verification.hit_at if verification else None,
            "hit_price": verification.hit_price if verification else None,
            "hit_target_index": verification.hit_target_index if verification else None,
            "reason": verification.reason if verification else "",
            "rule_match": status != "rejected",
            "risk_reward": _futures_risk_reward(record),
            "duplicate": bool(record.metadata.get("duplicate")),
            "requires_manual_review": bool(verification.requires_manual_review) if verification else False,
        },
        "raw_text": signal.raw_text,
    }


def _db_futures_signal_to_api(row: dict) -> dict:
    direction = str(row.get("direction") or "").lower()
    is_exit = direction == "exit"
    message_id = str(row.get("message_id") or row.get("id") or "")
    channel_key = str(row.get("channel_key") or "telegram")
    confidence = row.get("confidence")
    try:
        confidence_value = float(confidence) if confidence is not None else 0.65
    except (TypeError, ValueError):
        confidence_value = 0.65
    target_price = row.get("target_price")
    targets = [] if target_price in (None, "") else [target_price]
    status = "parsed"
    return {
        "id": f"{channel_key}-{message_id}",
        "internal_id": f"{channel_key}-{message_id}",
        "received_at": row.get("message_date"),
        "source": channel_key,
        "channel": channel_key,
        "symbol": row.get("symbol") or "-",
        "market": _futures_market_name(str(row.get("symbol") or "")),
        "side": "exit" if is_exit else ("buy" if direction == "long" else "sell"),
        "direction": direction or "-",
        "entry": row.get("entry_price"),
        "entry_price": row.get("entry_price"),
        "stop": row.get("stop_loss"),
        "stop_loss": row.get("stop_loss"),
        "targets": targets,
        "take_profit_1": target_price,
        "confidence": confidence_value,
        "parse_status": status,
        "status": status,
        "verification_status": "pending",
        "verification": {
            "status": "pending",
            "outcome": "pending",
            "hit_at": None,
            "hit_price": None,
            "hit_target_index": None,
            "reason": row.get("notes") or "",
            "rule_match": True,
            "risk_reward": None,
            "duplicate": False,
            "requires_manual_review": False,
        },
        "raw_text": row.get("raw_text") or "",
    }


def _list_db_futures_signals(limit: int | None = 100) -> list[dict]:
    try:
        from src.futures_signals import db as futures_signals_db

        rows = futures_signals_db.list_signals(limit=limit or 500)
    except Exception:
        return []
    return [_db_futures_signal_to_api(row) for row in rows]


def _futures_market_name(symbol: str) -> str:
    letters = "".join(char for char in symbol if char.isalpha())
    has_contract_year = any(char.isdigit() for char in symbol)
    root = letters[:-1] if has_contract_year and len(letters) > 1 else letters
    names = {
        "MNQ": "CME Micro E-mini Nasdaq-100",
        "NQ": "CME E-mini Nasdaq-100",
        "MES": "CME Micro E-mini S&P 500",
        "ES": "CME E-mini S&P 500",
        "MCL": "NYMEX Micro WTI Crude Oil",
        "CL": "NYMEX WTI Crude Oil",
        "MGC": "COMEX Micro Gold",
        "GC": "COMEX Gold",
    }
    return names.get(root, "Overseas futures")


def _find_futures_signal_record(public_or_internal_id: str):
    service = _get_futures_signal_service()
    direct = service.repository.get(public_or_internal_id)
    if direct is not None:
        return direct
    for record in service.list_records(limit=None):
        if _futures_signal_public_id(record) == public_or_internal_id:
            return record
    return None


def _futures_signals_summary(records: list, *, telegram_connected: bool = False) -> dict:
    signals = [
        _futures_signal_record_to_api(record) if not isinstance(record, dict) else record
        for record in records
    ]
    status_counts = {}
    for signal in signals:
        status = signal["status"]
        status_counts[status] = status_counts.get(status, 0) + 1
    latest = max((signal["received_at"] for signal in signals if signal.get("received_at")), default=None)
    total = len(signals)
    verified = status_counts.get("verified", 0)
    needs_review = (
        status_counts.get("needs_review", 0)
        + status_counts.get("pending", 0)
        + status_counts.get("parsed", 0)
    )
    rejected = status_counts.get("rejected", 0)
    confidence_values = [signal["confidence"] for signal in signals if signal.get("confidence") is not None]
    avg_confidence = sum(confidence_values) / len(confidence_values) if confidence_values else None
    win_rate = verified / (verified + rejected) if (verified + rejected) > 0 else None
    return {
        "as_of": trader.datetime.now(trader.KST).isoformat(),
        "source": "service",
        "telegram_connected": telegram_connected,
        "total": total,
        "verified": verified,
        "needs_review": needs_review,
        "rejected": rejected,
        "parse_success_rate": 1.0 if total else None,
        "win_rate": win_rate,
        "avg_parse_confidence": avg_confidence,
        "avg_pnl_points": None,
        "status_counts": status_counts,
        "latest_signal_at": latest,
        "performance": {
            "labels": [str(signal.get("received_at") or "")[11:16] for signal in signals[:20]][::-1],
            "pnl": [0 for _ in signals[:20]][::-1],
            "win_rate": [0 for _ in signals[:20]][::-1],
        },
    }


def _read_json_file(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def _quantconnect_auth_status(credentials: QuantConnectCredentials) -> dict:
    now = trader.datetime.now(trader.KST)
    cached = _read_json_file(QUANTCONNECT_AUTH_CACHE, {})
    if not isinstance(cached, dict):
        cached = {}
    cached_at = cached.get("checked_at")
    if cached_at:
        try:
            age = (now - trader.datetime.fromisoformat(cached_at)).total_seconds()
        except ValueError:
            age = None
        if age is not None and age < 300:
            status = cached.get("status", {})
            if status:
                return {**status, "cached": True}

    status = QuantConnectAPI(credentials).authenticate(timeout=5.0)
    QUANTCONNECT_AUTH_CACHE.parent.mkdir(parents=True, exist_ok=True)
    QUANTCONNECT_AUTH_CACHE.write_text(
        json.dumps({"checked_at": now.isoformat(), "status": status}, ensure_ascii=False),
        encoding="utf-8",
    )
    return {**status, "cached": False}


def _first_item(value):
    if isinstance(value, list):
        return value[0] if value else {}
    if isinstance(value, dict):
        return value
    return {}


def _quantconnect_errors(*payloads: dict) -> list[str]:
    errors = []
    for payload in payloads:
        if not isinstance(payload, dict):
            continue
        for error in payload.get("errors") or []:
            if error:
                errors.append(str(error))
        if payload.get("error"):
            errors.append(str(payload["error"]))
        if payload.get("message") and payload.get("success") is False:
            errors.append(str(payload["message"]))
    return list(dict.fromkeys(errors))


def _quantconnect_order_rows(payload: dict) -> list[dict]:
    orders = payload.get("orders") or payload.get("Orders") or []
    if isinstance(orders, dict):
        orders = list(orders.values())
    rows = []
    for order in orders if isinstance(orders, list) else []:
        if not isinstance(order, dict):
            continue
        symbol = order.get("symbol") or order.get("Symbol") or "MNQ"
        if isinstance(symbol, dict):
            symbol = symbol.get("value") or symbol.get("id") or symbol.get("permtick") or "MNQ"
        direction = order.get("direction") or order.get("side") or order.get("Direction")
        if direction in {0, "0"}:
            direction = "Buy"
        elif direction in {1, "1"}:
            direction = "Sell"
        elif direction is None and (order.get("quantity") or order.get("Quantity") or 0):
            direction = "Buy" if float(order.get("quantity") or order.get("Quantity") or 0) > 0 else "Sell"
        rows.append({
            "id": order.get("id") or order.get("orderId") or order.get("OrderId"),
            "time": order.get("time") or order.get("createdTime") or order.get("lastFillTime") or order.get("Time"),
            "symbol": symbol,
            "side": direction,
            "quantity": order.get("quantity") or order.get("Quantity"),
            "price": order.get("price") or order.get("Price") or order.get("averageFillPrice"),
            "status": order.get("status") or order.get("Status"),
        })
    return rows


def _quantconnect_portfolio_state(payload: dict) -> dict:
    portfolio = payload.get("portfolio") or payload.get("Portfolio") or {}
    holdings_raw = portfolio.get("holdings") if isinstance(portfolio, dict) else {}
    cash_raw = portfolio.get("cash") if isinstance(portfolio, dict) else {}
    holdings = []
    if isinstance(holdings_raw, dict):
        iterator = holdings_raw.items()
    elif isinstance(holdings_raw, list):
        iterator = enumerate(holdings_raw)
    else:
        iterator = []
    for key, value in iterator:
        if not isinstance(value, dict):
            continue
        holdings.append({
            "symbol": value.get("symbol") or value.get("Symbol") or str(key),
            "quantity": value.get("quantity") or value.get("Quantity") or value.get("holdings") or value.get("q"),
            "average_price": value.get("averagePrice") or value.get("AveragePrice") or value.get("a"),
            "market_price": value.get("price") or value.get("Price") or value.get("p"),
            "market_value": value.get("marketValue") or value.get("MarketValue") or value.get("value") or value.get("v"),
            "unrealized_pnl": value.get("unrealizedProfit") or value.get("UnrealizedProfit") or value.get("u"),
        })
    return {
        "raw": portfolio if isinstance(portfolio, dict) else {},
        "holdings": holdings,
        "cash": cash_raw if isinstance(cash_raw, dict) else {},
        "total_portfolio_value": portfolio.get("totalPortfolioValue") if isinstance(portfolio, dict) else None,
    }


def _quantconnect_cloud_snapshot(credentials: QuantConnectCredentials, *, force_refresh: bool = False) -> dict:
    if not credentials.configured or not credentials.project_configured:
        return {
            "enabled": False,
            "errors": [],
            "project": {},
            "live": {},
            "portfolio": {},
            "orders": [],
        }

    now = trader.datetime.now(trader.KST)
    cached = _read_json_file(QUANTCONNECT_CLOUD_CACHE, {})
    if not force_refresh and isinstance(cached, dict) and cached.get("checked_at"):
        try:
            age = (now - trader.datetime.fromisoformat(cached["checked_at"])).total_seconds()
        except ValueError:
            age = None
        if age is not None and age < 60 and isinstance(cached.get("snapshot"), dict):
            snapshot = cached["snapshot"]
            snapshot["cached"] = True
            return snapshot

    api = QuantConnectAPI(credentials)
    project_payload = api.read_project(credentials.project_id, timeout=8.0)
    live_list_payload = api.list_live_algorithms(credentials.project_id, timeout=8.0)
    live_payload = api.read_live_algorithm(credentials.project_id, timeout=8.0)
    portfolio_payload = api.read_live_portfolio(credentials.project_id, timeout=8.0)

    projects = project_payload.get("projects") if isinstance(project_payload, dict) else []
    project = _first_item(projects)
    live_algorithms = (
        live_list_payload.get("live") or
        live_list_payload.get("algorithms") or
        live_list_payload.get("liveAlgorithms") or
        []
    )
    live_algorithm = _first_item(live_algorithms)
    deploy_id = (
        live_payload.get("deployId") or
        live_payload.get("algorithmId") or
        live_algorithm.get("deployId") or
        live_algorithm.get("algorithmId")
        if isinstance(live_payload, dict)
        else None
    )

    orders_payload = {}
    if deploy_id:
        orders_payload = api.read_live_orders(credentials.project_id, deploy_id, start=0, end=100, timeout=8.0)

    portfolio = _quantconnect_portfolio_state(portfolio_payload if isinstance(portfolio_payload, dict) else {})
    snapshot = {
        "enabled": True,
        "cached": False,
        "project": {
            "id": project.get("projectId") or credentials.project_id,
            "name": project.get("name") or project.get("Name") or "",
            "modified": project.get("modified") or project.get("Modified") or "",
            "language": project.get("language") or project.get("Language") or "",
        },
        "live": {
            "status": live_payload.get("status") or live_algorithm.get("status"),
            "deploy_id": deploy_id,
            "message": live_payload.get("message") or live_algorithm.get("message"),
            "launched": live_payload.get("launched") or live_algorithm.get("launched"),
            "stopped": live_payload.get("stopped") or live_algorithm.get("stopped"),
            "brokerage": live_payload.get("brokerage") or live_algorithm.get("brokerage"),
        },
        "portfolio": portfolio,
        "orders": _quantconnect_order_rows(orders_payload if isinstance(orders_payload, dict) else {}),
        "api_errors": _quantconnect_errors(project_payload, live_list_payload, live_payload, portfolio_payload, orders_payload),
    }
    QUANTCONNECT_CLOUD_CACHE.parent.mkdir(parents=True, exist_ok=True)
    QUANTCONNECT_CLOUD_CACHE.write_text(
        json.dumps({"checked_at": now.isoformat(), "snapshot": snapshot}, ensure_ascii=False),
        encoding="utf-8",
    )
    return snapshot


def _clear_quantconnect_cloud_cache() -> None:
    try:
        QUANTCONNECT_CLOUD_CACHE.unlink(missing_ok=True)
    except OSError:
        pass


def _quantconnect_live_nodes(nodes_payload: dict) -> list[dict]:
    nodes = nodes_payload.get("nodes") if isinstance(nodes_payload, dict) else {}
    live_nodes = nodes.get("live") if isinstance(nodes, dict) else []
    return [node for node in live_nodes if isinstance(node, dict)]


def _select_quantconnect_live_node(nodes_payload: dict, requested_node_id: str = "") -> dict:
    live_nodes = _quantconnect_live_nodes(nodes_payload)
    if requested_node_id:
        for node in live_nodes:
            if str(node.get("id") or "") == requested_node_id:
                return node
        raise HTTPException(status_code=400, detail=f"QuantConnect live node not found: {requested_node_id}")

    for node in live_nodes:
        if node.get("active") and not node.get("busy"):
            return node
    for node in live_nodes:
        if node.get("active"):
            return node
    if live_nodes:
        return live_nodes[0]
    raise HTTPException(status_code=409, detail="No QuantConnect live node is available for this project")


def _wait_for_quantconnect_compile(
    api: QuantConnectAPI,
    project_id: str,
    compile_payload: dict,
    *,
    attempts: int = 12,
    interval_seconds: float = 2.0,
) -> dict:
    compile_id = str(compile_payload.get("compileId") or "")
    if not compile_id:
        errors = compile_payload.get("errors") or [compile_payload.get("error") or "QuantConnect compile did not return compileId"]
        raise HTTPException(status_code=502, detail="; ".join(str(error) for error in errors if error))

    result = compile_payload
    for _ in range(attempts):
        state = str(result.get("state") or "").lower()
        if state == "buildsuccess":
            return result
        if state == "builderror":
            logs = result.get("logs") or result.get("errors") or ["QuantConnect build failed"]
            raise HTTPException(status_code=502, detail="; ".join(str(log) for log in logs if log))
        time.sleep(interval_seconds)
        result = api.read_compile(project_id, compile_id, timeout=10.0)

    raise HTTPException(status_code=504, detail=f"QuantConnect compile is still pending: {compile_id}")


def _quantconnect_mnq_status() -> dict:
    load_dotenv(dotenv_path=ENV_PATH, override=True)
    algorithm_path = QUANTCONNECT_MNQ_DIR / "main.py"
    config_path = QUANTCONNECT_MNQ_DIR / "config.json"
    doc_path = BASE_DIR / "doc" / "S1.한스톡사용설명서.md"
    config = _read_json_file(config_path, {})
    if not isinstance(config, dict):
        config = {}
    results = _read_json_file(QUANTCONNECT_MNQ_RESULTS, {})
    if not isinstance(results, dict):
        results = {}
    qc_user_id = os.environ.get("QUANTCONNECT_USER_ID") or os.environ.get("QC_USER_ID")
    qc_api_token = os.environ.get("QUANTCONNECT_API_TOKEN") or os.environ.get("QC_API_TOKEN")
    qc_project_id = os.environ.get("QUANTCONNECT_PROJECT_ID") or os.environ.get("QC_PROJECT_ID")
    credentials = QuantConnectCredentials(
        user_id=qc_user_id or "",
        api_token=qc_api_token or "",
        project_id=qc_project_id or "",
    )
    auth = _quantconnect_auth_status(credentials)
    cloud_sync_configured = credentials.configured and credentials.project_configured
    cloud_snapshot = _quantconnect_cloud_snapshot(credentials)
    project_ready = algorithm_path.exists() and config_path.exists()

    deployment = results.get("deployment") if isinstance(results.get("deployment"), dict) else {}
    if not deployment:
        cloud_live = cloud_snapshot.get("live", {}) if isinstance(cloud_snapshot.get("live"), dict) else {}
        cloud_status = str(cloud_live.get("status") or "").strip()
        if cloud_status:
            if cloud_status.lower() == "running":
                deployment_status = "running"
                deployment_message = "QuantConnect Paper Live deployment is running."
            else:
                deployment_status = cloud_status.lower()
                deployment_message = (
                    f"QuantConnect project is configured, but the Paper Live deployment is {cloud_status}. "
                    "Start or redeploy it before sending dashboard orders."
                )
        elif not credentials.configured:
            deployment_status = "not_connected"
            deployment_message = "QuantConnect User Id and API Token are required."
        elif not credentials.project_configured:
            deployment_status = "not_connected"
            deployment_message = "QuantConnect Project Id is required for project/order sync."
        else:
            deployment_status = "ready_to_sync"
            deployment_message = "QuantConnect API and Project Id are configured. Deploy the project as Paper Live before sending dashboard orders."
        deployment = {
            "status": deployment_status,
            "message": deployment_message,
        }

    return {
        "as_of": trader.datetime.now(trader.KST).isoformat(),
        "feasible": True,
        "project_ready": project_ready,
        "cloud_sync_configured": cloud_sync_configured,
        "auth": {
            "configured": credentials.configured,
            "project_configured": credentials.project_configured,
            "success": bool(auth.get("success")),
            "status_code": auth.get("status_code"),
            "error": auth.get("error"),
        },
        "algorithm": {
            "path": str(algorithm_path),
            "exists": algorithm_path.exists(),
            "symbol": "MNQ",
            "quantconnect_symbol": "Futures.Indices.MICRO_NASDAQ_100_E_MINI",
            "brokerage": "QuantConnect Paper Trading",
            "max_contracts": config.get("parameters", {}).get("MAX_CONTRACTS", "1"),
        },
        "files": {
            "config": {"path": str(config_path), "exists": config_path.exists()},
            "documentation": {"path": str(doc_path), "exists": doc_path.exists()},
            "results": {"path": str(QUANTCONNECT_MNQ_RESULTS), "exists": QUANTCONNECT_MNQ_RESULTS.exists()},
        },
        "deployment": deployment,
        "account": cloud_snapshot.get("portfolio", {}).get("raw") or results.get("account", {}),
        "positions": cloud_snapshot.get("portfolio", {}).get("holdings") or results.get("positions", []),
        "orders": cloud_snapshot.get("orders") or results.get("orders", []),
        "metrics": results.get("metrics", {}),
        "cloud": cloud_snapshot,
        "sources": [
            "https://www.quantconnect.com/docs/v2/cloud-platform/live-trading/brokerages/quantconnect-paper-trading",
            "https://www.quantconnect.com/docs/v2/writing-algorithms/datasets/algoseek/us-futures",
        ],
    }


def _quantconnect_credentials() -> QuantConnectCredentials:
    load_dotenv(dotenv_path=ENV_PATH, override=True)
    return QuantConnectCredentials(
        user_id=os.environ.get("QUANTCONNECT_USER_ID") or os.environ.get("QC_USER_ID") or "",
        api_token=os.environ.get("QUANTCONNECT_API_TOKEN") or os.environ.get("QC_API_TOKEN") or "",
        project_id=os.environ.get("QUANTCONNECT_PROJECT_ID") or os.environ.get("QC_PROJECT_ID") or "",
    )


def _quantconnect_mnq_deploy(payload: dict | None = None) -> dict:
    payload = payload or {}
    credentials = _quantconnect_credentials()
    if not credentials.configured:
        raise HTTPException(status_code=400, detail="QuantConnect User Id and API Token are required")
    if not credentials.project_configured:
        raise HTTPException(status_code=400, detail="QUANTCONNECT_PROJECT_ID is required")

    api = QuantConnectAPI(credentials)
    requested_node_id = (
        str(payload.get("node_id") or "").strip()
        or os.environ.get("QUANTCONNECT_LIVE_NODE_ID", "").strip()
        or os.environ.get("QC_LIVE_NODE_ID", "").strip()
    )

    nodes_payload = api.read_project_nodes(credentials.project_id, timeout=10.0)
    if not nodes_payload.get("success", False):
        errors = nodes_payload.get("errors") or [nodes_payload.get("error") or "QuantConnect live node lookup failed"]
        raise HTTPException(status_code=502, detail="; ".join(str(error) for error in errors if error))
    node = _select_quantconnect_live_node(nodes_payload, requested_node_id)

    compile_payload = api.create_compile(credentials.project_id, timeout=10.0)
    if not compile_payload.get("success", False):
        errors = compile_payload.get("errors") or [compile_payload.get("error") or "QuantConnect compile failed"]
        raise HTTPException(status_code=502, detail="; ".join(str(error) for error in errors if error))
    compile_result = _wait_for_quantconnect_compile(api, credentials.project_id, compile_payload)

    config = _read_json_file(QUANTCONNECT_MNQ_DIR / "config.json", {})
    parameters = config.get("parameters", {}) if isinstance(config, dict) else {}
    live_payload = api.create_live_algorithm(
        credentials.project_id,
        str(compile_result.get("compileId")),
        str(node.get("id")),
        parameters=parameters,
        timeout=20.0,
    )
    if not live_payload.get("success", False):
        errors = live_payload.get("errors") or [live_payload.get("error") or "QuantConnect Paper Live deployment failed"]
        raise HTTPException(status_code=502, detail="; ".join(str(error) for error in errors if error))

    _clear_quantconnect_cloud_cache()
    snapshot = _quantconnect_cloud_snapshot(credentials, force_refresh=True)
    return {
        "success": True,
        "project_id": credentials.project_id,
        "compile_id": compile_result.get("compileId"),
        "node": {
            "id": node.get("id"),
            "name": node.get("name"),
            "sku": node.get("sku"),
        },
        "deploy_id": live_payload.get("deployId") or live_payload.get("algorithmId"),
        "raw": live_payload,
        "cloud": snapshot,
    }


def _quantconnect_mnq_order(payload: dict) -> dict:
    credentials = _quantconnect_credentials()
    side = str(payload.get("side") or "").strip().lower()
    signal_id = str(payload.get("signal_id") or "").strip()
    provider = str(payload.get("provider") or "").strip()
    try:
        quantity = int(payload.get("quantity") or payload.get("qty") or 0)
    except (TypeError, ValueError):
        quantity = 0

    if side not in {"buy", "sell"}:
        raise HTTPException(status_code=400, detail="side must be buy or sell")
    if quantity < 1:
        raise HTTPException(status_code=400, detail="quantity must be at least 1")
    if quantity > 3:
        raise HTTPException(status_code=400, detail="MNQ paper dashboard orders are limited to 3 contracts")
    if not credentials.configured:
        raise HTTPException(status_code=400, detail="QuantConnect User Id and API Token are required")
    if not credentials.project_configured:
        raise HTTPException(status_code=400, detail="QUANTCONNECT_PROJECT_ID is required")

    cloud_snapshot = _quantconnect_cloud_snapshot(credentials, force_refresh=True)
    live = cloud_snapshot.get("live", {}) if isinstance(cloud_snapshot.get("live"), dict) else {}
    live_status = str(live.get("status") or "").strip()
    if live_status.lower() != "running":
        detail = (
            f"QuantConnect project {credentials.project_id} has no running Paper Live instance"
        )
        if live_status:
            detail += f" (current status: {live_status})"
        detail += ". Start or redeploy the project in QuantConnect before sending dashboard orders."
        raise HTTPException(status_code=409, detail=detail)

    order_tag = "hanstock-dashboard-mnq-paper"
    if signal_id:
        tag_source = re.sub(r"[^A-Za-z0-9_-]+", "-", provider or "telegram").strip("-") or "telegram"
        signal_ref = re.sub(r"[^A-Za-z0-9_-]+", "-", signal_id).strip("-") or "signal"
        order_tag = f"hanstock-signal-{tag_source}-{signal_ref}"[:80]

    command = {
        "command_type": "order",
        "symbol": "MNQ",
        "side": side,
        "quantity": quantity,
        "tag": order_tag,
    }
    result = QuantConnectAPI(credentials).create_live_command(credentials.project_id, command, timeout=10.0)
    return {
        "success": bool(result.get("success")),
        "command": command,
        "status_code": result.get("status_code"),
        "error": result.get("error"),
        "errors": result.get("errors", []),
    }


def _license_name(text: str, hint: str) -> str:
    lowered = text.lower()
    if "gnu general public license" in lowered:
        return "GPL-3.0"
    if "mit license" in lowered:
        return "MIT"
    if "apache license" in lowered:
        return "Apache-2.0"
    return hint or "unknown"


def _vendor_status(slug: str, meta: dict) -> dict:
    root = meta["path"]
    exists = root.exists()
    license_path = root / "LICENSE"
    if not license_path.exists():
        license_path = root / "LICENSE.txt"
    license_text = license_path.read_text(encoding="utf-8", errors="replace") if license_path.exists() else ""
    files = list(root.rglob("*")) if exists else []
    pkg = root / meta["package"]
    modules = []
    if pkg.exists():
        modules = [
            child.name
            for child in sorted(pkg.iterdir())
            if child.is_dir() and not child.name.startswith("__")
        ]
    return {
        "slug": slug,
        "name": meta["name"],
        "exists": exists,
        "path": str(root),
        "license": _license_name(license_text, meta["license_hint"]),
        "license_notice": license_text[:500],
        "file_count": len([path for path in files if path.is_file()]),
        "python_file_count": len([path for path in files if path.suffix == ".py"]),
        "notebook_count": len([path for path in files if path.suffix == ".ipynb"]),
        "modules": modules,
        "adapter": meta["adapter"],
        "entrypoints": meta["entrypoints"],
        "dashboard": meta["dashboard"],
    }


def _demo_trading_readiness() -> dict:
    missing = _required_env_missing()
    account_warning = _account_format_warning(trader.config.kistock_account)
    checks = [
        {
            "key": "required_env",
            "ok": not missing,
            "message": "Required KIS environment values are configured" if not missing else f"Missing: {', '.join(missing)}",
            "critical": True,
        },
        {
            "key": "account_format",
            "ok": not account_warning,
            "message": "KIS account format is valid" if not account_warning else account_warning,
            "critical": True,
        },
        {
            "key": "demo_environment",
            "ok": trader.TRADING_ENV == "demo",
            "message": f"TRADING_ENV={trader.TRADING_ENV}",
            "critical": True,
        },
        {
            "key": "dry_run_disabled",
            "ok": trader.DRY_RUN is False,
            "message": f"DRY_RUN={str(trader.DRY_RUN).lower()}",
            "critical": True,
        },
        {
            "key": "live_trading_disabled",
            "ok": trader.ENABLE_LIVE_TRADING is False and trader.REAL_ORDERS_ENABLED is False,
            "message": f"ENABLE_LIVE_TRADING={str(trader.ENABLE_LIVE_TRADING).lower()}, real_orders={str(trader.REAL_ORDERS_ENABLED).lower()}",
            "critical": True,
        },
        {
            "key": "demo_order_submission",
            "ok": trader.ORDER_SUBMISSION_ENABLED is True,
            "message": f"ORDER_SUBMISSION_ENABLED={str(trader.ORDER_SUBMISSION_ENABLED).lower()}",
            "critical": True,
        },
        {
            "key": "kill_switch",
            "ok": not Path(".runtime/kill_switch.json").exists(),
            "message": "Kill switch is inactive" if not Path(".runtime/kill_switch.json").exists() else "Kill switch is active",
            "critical": False,
        },
        {
            "key": "approval_policy",
            "ok": trader.REQUIRE_APPROVAL or _auto_approval_enabled(),
            "message": f"REQUIRE_APPROVAL={str(trader.REQUIRE_APPROVAL).lower()}, auto_approval={str(_auto_approval_enabled()).lower()}",
            "critical": False,
        },
    ]
    critical_ready = all(item["ok"] for item in checks if item["critical"])
    return {
        "ready": critical_ready,
        "mode": "kis_demo_auto",
        "trading_env": trader.TRADING_ENV,
        "dry_run": trader.DRY_RUN,
        "enable_live_trading": trader.ENABLE_LIVE_TRADING,
        "order_submission_enabled": trader.ORDER_SUBMISSION_ENABLED,
        "real_orders_enabled": trader.REAL_ORDERS_ENABLED,
        "checks": checks,
    }


def _runtime_dashboard_info() -> dict:
    hostname = socket.gethostname()
    explicit_label = os.environ.get("HANSTOCK_DASHBOARD_LABEL", "").strip()
    explicit_origin = os.environ.get("HANSTOCK_DASHBOARD_ORIGIN", "").strip().lower()
    is_vm = explicit_origin == "vm" or hostname.startswith("hanstock-server")
    label = explicit_label or ("VM DASHBOARD" if is_vm else "LOCAL DASHBOARD")
    return {
        "label": label,
        "origin": "vm" if is_vm else "local",
        "is_vm": is_vm,
        "hostname": hostname,
    }


@app.get("/api/health")
def health():
    missing = _required_env_missing()
    account_warning = _account_format_warning(trader.config.kistock_account)
    demo_readiness = _demo_trading_readiness()
    from src.db.repository import _load_token_usage
    return {
        "ok": not missing and not account_warning,
        "missing": missing,
        "account_warning": account_warning,
        "trading_env": trader.TRADING_ENV,
        "dry_run": trader.DRY_RUN,
        "enable_live_trading": trader.ENABLE_LIVE_TRADING,
        "require_approval": trader.REQUIRE_APPROVAL,
        "order_submission_enabled": trader.ORDER_SUBMISSION_ENABLED,
        "real_orders_enabled": trader.REAL_ORDERS_ENABLED,
        "circuit_breaker": KIStockAPI.circuit_status(),
        "active_model_version": getattr(trader.config, "active_model_version", "v1"),
        "ai_analysis": _ai_analysis_config(),
        "auto_approval_enabled": _auto_approval_enabled(),
        "demo_trading_ready": demo_readiness["ready"],
        "demo_trading_readiness": demo_readiness,
        "kill_switch_active": Path(".runtime/kill_switch.json").exists(),
        "dashboard_runtime": _runtime_dashboard_info(),
        "token_usage": _load_token_usage(),
    }


@app.get("/api/demo-trading/readiness")
def get_demo_trading_readiness():
    return _demo_trading_readiness()


@app.get("/api/futures-signals/summary")
def get_futures_signals_summary():
    db_signals = _list_db_futures_signals(limit=500)
    if db_signals:
        return _futures_signals_summary(db_signals, telegram_connected=True)
    records = _get_futures_signal_service().list_records(limit=None)
    return _futures_signals_summary(records)


@app.get("/api/quantconnect/mnq/status")
def get_quantconnect_mnq_status():
    return _quantconnect_mnq_status()


@app.post("/api/quantconnect/mnq/order")
def place_quantconnect_mnq_order(payload: dict = Body(...)):
    return _quantconnect_mnq_order(payload)


@app.post("/api/quantconnect/mnq/deploy")
def deploy_quantconnect_mnq(payload: dict | None = Body(default=None)):
    return _quantconnect_mnq_deploy(payload)


@app.get("/api/mock-trading/summary")
def get_mock_trading_summary():
    """모의거래 성과 요약"""
    import os
    json_path = Path(".runtime/mock_trades.json")
    if not json_path.exists():
        return {
            "open_positions": 0,
            "closed_trades": 0,
            "total_pnl": 0,
            "win_rate": 0,
            "wins": 0,
            "losses": 0,
            "positions": [],
            "recent_trades": []
        }
    
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    positions = data.get("positions", [])
    history = data.get("history", [])
    
    total_pnl = sum(h.get("pnl", 0) for h in history)
    wins = sum(1 for h in history if h.get("pnl", 0) > 0)
    losses = sum(1 for h in history if h.get("pnl", 0) <= 0)
    total_trades = len(history)
    win_rate = (wins / total_trades * 100) if total_trades > 0 else 0
    
    return {
        "open_positions": len(positions),
        "closed_trades": total_trades,
        "total_pnl": round(total_pnl, 4),
        "win_rate": round(win_rate, 1),
        "wins": wins,
        "losses": losses,
        "positions": positions,
        "recent_trades": history[-10:] if history else []
    }


@app.get("/api/mock-trading/positions")
def get_mock_trading_positions():
    """모의거래 현재 포지션"""
    import os
    from datetime import datetime
    import requests
    
    json_path = Path(".runtime/mock_trades.json")
    if not json_path.exists():
        return {"positions": []}
    
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    positions = data.get("positions", [])
    
    # 실시간 시세 조회
    try:
        resp = requests.get("https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT", timeout=5)
        current_price = float(resp.json()["price"])
    except:
        current_price = 0
    
    # PnL 계산
    for pos in positions:
        if pos.get("symbol") == "BTC" and current_price:
            entry = pos.get("entry_price", 0)
            qty = pos.get("qty", 0)
            if pos.get("side") == "LONG":
                pnl = (current_price - entry) * qty
            else:
                pnl = (entry - current_price) * qty
            pos["current_price"] = current_price
            pos["current_pnl"] = round(pnl, 4)
    
    return {"positions": positions, "current_price": current_price}


@app.get("/api/mock-trading/trades")
def get_mock_trading_trades(limit: int = 200):
    """모의거래 체결 내역"""
    json_path = Path(".runtime/mock_trades.json")
    if not json_path.exists():
        return {"trades": []}
    try:
        data = json.loads(json_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"error": str(exc), "trades": []}
    history = data.get("history", [])
    if not isinstance(history, list):
        history = []
    safe_limit = max(1, min(int(limit or 200), 1000))
    return {"trades": history[-safe_limit:][::-1]}


@app.get("/api/futures-signals")
def get_futures_signals(limit: int = 100):
    safe_limit = max(1, min(int(limit or 100), 500))
    db_signals = _list_db_futures_signals(limit=safe_limit)
    if db_signals:
        return {"signals": db_signals}
    records = _get_futures_signal_service().list_records(limit=safe_limit)
    return {"signals": [_futures_signal_record_to_api(record) for record in records]}


@app.get("/api/futures-signals/collector/status")
def get_futures_signal_collector_status():
    status = collector_status()
    # `connected`: session이 있고 ready이면 연결된 것으로 간주
    status.setdefault("connected", bool(status.get("ready") and status.get("session_available")))
    # `running`: poll.py 프로세스가 실제로 실행 중인지 확인
    status["running"] = _is_poll_running()
    return status


@app.post("/api/futures-signals/collector/run")
async def run_futures_signal_collector(payload: dict | None = Body(default=None)):
    payload = payload or {}
    status = collector_status()
    if not status["ready"]:
        return {**status, "ok": False, "ingested": 0}

    limit = max(1, min(int(payload.get("limit_per_channel", 50) or 50), 200))
    try:
        messages = await TelegramSignalCollector().fetch_recent_messages(limit_per_channel=limit)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    from src.futures_signals import db as futures_signals_db

    ingested = 0
    parse_errors = []
    for message in messages:
        if message.get("collector_error"):
            parse_errors.append({
                "channel": message.get("channel"),
                "error": message.get("collector_error"),
            })
            continue
        try:
            raw_text = str(message.get("raw_text") or "")
            channel = str(message.get("channel") or "telegram")
            msg_id = message.get("telegram_message_id") or 0
            msg_date = message.get("received_at") or ""

            # parser로 파싱 시도
            parsed = None
            try:
                from src.futures_signals.parser import parse_signal
                parsed = parse_signal(raw_text)
            except Exception:
                pass

            inserted = futures_signals_db.insert_signal(
                channel_key=channel,
                message_id=int(msg_id) if str(msg_id).isdigit() else 0,
                message_date=msg_date,
                raw_text=raw_text,
                symbol=parsed.symbol if parsed else None,
                direction=parsed.direction if parsed else None,
                entry_price=parsed.entry if parsed else None,
                stop_loss=parsed.stop_loss if parsed else None,
                target_price=parsed.take_profits[0] if parsed and parsed.take_profits else None,
                confidence=None,
                notes=None,
            )
            if inserted:
                ingested += 1
        except Exception as exc:
            parse_errors.append({
                "telegram_message_id": message.get("telegram_message_id"),
                "error": str(exc),
            })
    return {
        "ok": True,
        "ingested": ingested,
        "parse_errors": parse_errors,
        "collector": status,
    }


@app.post("/api/futures-signals/collector/settings")
async def save_collector_settings(request: Request):
    """Telegram 설정 저장 - .env 파일에 기록"""
    body = await request.json()

    env_path = Path(".env")

    # 기존 .env 읽기
    if env_path.exists():
        lines = env_path.read_text(encoding="utf-8").splitlines()
    else:
        lines = []

    # 업데이트할 키-값 쌍
    updates = {}
    if "api_id" in body:
        updates["TELEGRAM_API_ID"] = str(body["api_id"])
    if "api_hash" in body:
        updates["TELEGRAM_API_HASH"] = str(body["api_hash"])
    if "channels" in body:
        updates["TELEGRAM_TARGET_CHANNELS"] = str(body["channels"])

    # 기존 라인에서 해당 키 업데이트
    new_lines = []
    updated_keys = set()
    for line in lines:
        stripped = line.strip()
        if "=" in stripped and not stripped.startswith("#"):
            key = stripped.split("=", 1)[0].strip()
            if key in updates:
                new_lines.append(f'{key}={updates[key]}')
                updated_keys.add(key)
            else:
                new_lines.append(line)
        else:
            new_lines.append(line)

    # 새 키 추가
    for key, val in updates.items():
        if key not in updated_keys:
            new_lines.append(f'{key}={val}')

    env_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")

    return {"ok": True, "message": "설정이 저장되었습니다. 서버를 재시작하면 적용됩니다."}


@app.post("/api/futures-signals/parse")
def parse_futures_signal_message(payload: dict = Body(...)):
    text = str(payload.get("text") or payload.get("raw_text") or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="text is required")
    source = str(payload.get("source") or "telegram_manual")
    source_message_id = payload.get("source_message_id")
    received_at = payload.get("received_at")
    parsed_received_at = None
    if received_at:
        try:
            parsed_received_at = trader.datetime.fromisoformat(str(received_at))
        except ValueError:
            raise HTTPException(status_code=400, detail="received_at must be ISO-8601")
    try:
        record = _get_futures_signal_service().ingest_message(
            text,
            source=source,
            source_message_id=str(source_message_id) if source_message_id else None,
            received_at=parsed_received_at,
        )
    except FuturesSignalParseError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"signal": _futures_signal_record_to_api(record)}


@app.post("/api/futures-signals/{signal_id}/verify")
def verify_futures_signal(signal_id: str, payload: dict = Body(...)):
    record = _find_futures_signal_record(signal_id)
    if record is None:
        raise HTTPException(status_code=404, detail="futures signal not found")

    candles_payload = payload.get("candles") or []
    if not isinstance(candles_payload, list) or not candles_payload:
        raise HTTPException(status_code=400, detail="candles list is required")

    candles = []
    for item in candles_payload:
        try:
            candles.append(
                OhlcCandle(
                    timestamp=item.get("timestamp") or item.get("time") or "",
                    open=float(item["open"]),
                    high=float(item["high"]),
                    low=float(item["low"]),
                    close=float(item["close"]),
                )
            )
        except (KeyError, TypeError, ValueError):
            raise HTTPException(status_code=400, detail="each candle must include open/high/low/close")

    updated = _get_futures_signal_service().verify(record.signal.id, candles)
    if updated is None:
        raise HTTPException(status_code=404, detail="futures signal not found")
    return {"signal": _futures_signal_record_to_api(updated)}

# =============================================================================
# KIS 해외선물optsms Trading API
# =============================================================================

def _get_futures_api():
    from src.api.kis_futures_api import KISFuturesAPI
    return KISFuturesAPI()


@app.get("/api/futures/balance")
def get_futures_balance():
    try:
        api = _get_futures_api()
        result = api.get_balance()
        if result.get("rt_cd") != "0":
            return {"error": result.get("msg1", "failed"), "data": None}
        output = result.get("output", {})
        return {
            "raw": output,
            "cash": output.get("mnres_krw") or output.get("frcr_dncl_amt") or output.get("frcr_buy_amt_smtl") or "미확인",
            "total_assets": output.get("tot_asst") or output.get("evlu_amt_smtl") or "미확인",
            "margin": output.get("mgn") or "미확인",
            "orderable_cash": output.get("ord_cash") or "미확인",
            "status": "ok" if output else "no_data",
        }
    except Exception as e:
        return {"error": str(e), "data": None}


@app.get("/api/futures/positions")
def get_futures_positions():
    try:
        api = _get_futures_api()
        result = api.get_positions()
        if result.get("rt_cd") != "0":
            return {"error": result.get("msg1", "failed"), "positions": []}
        output = result.get("output", [])
        if not isinstance(output, list):
            output = [output] if output else []
        return {"positions": output}
    except Exception as e:
        return {"error": str(e), "positions": []}


@app.get("/api/futures/orders")
def get_futures_orders(start_date: str = None, end_date: str = None):
    try:
        api = _get_futures_api()
        result = api.get_daily_orders(start_date, end_date)
        if result.get("rt_cd") != "0":
            return {"error": result.get("msg1", "failed"), "orders": []}
        output = result.get("output1", [])
        if not isinstance(output, list):
            output = [output] if output else []
        return {"orders": output}
    except Exception as e:
        return {"error": str(e), "orders": []}


@app.get("/api/futures/quote/{symbol}")
def get_futures_quote(symbol: str):
    try:
        api = _get_futures_api()
        result = api.get_current_price(symbol)
        if result.get("rt_cd") != "0":
            return {"error": result.get("msg1", "failed"), "quote": None}
        return {"quote": result.get("output1", {})}
    except Exception as e:
        return {"error": str(e), "quote": None}


@app.post("/api/futures/order")
def place_futures_order(payload: dict = Body(...)):
    try:
        api = _get_futures_api()
        symbol = payload.get("symbol")
        order_type = payload.get("type")
        qty = payload.get("qty")
        price = payload.get("price", "0")
        if not all([symbol, order_type, qty]):
            raise HTTPException(status_code=400, detail="symbol, type, qty required")
        result = api.place_order(symbol, order_type, int(qty), price)
        if result.get("rt_cd") != "0":
            return {"error": result.get("msg1", "order failed"), "success": False}
        return {"success": True, "order_no": result.get("output", {}).get("ODNO", "")}
    except HTTPException:
        raise
    except Exception as e:
        return {"error": str(e), "success": False}


@app.post("/api/futures/order/cancel")
def cancel_futures_order(payload: dict = Body(...)):
    try:
        api = _get_futures_api()
        order_no = payload.get("order_no")
        order_date = payload.get("order_date", "")
        if not order_no:
            raise HTTPException(status_code=400, detail="order_no required")
        result = api.cancel_order(order_no, order_date)
        if result.get("rt_cd") != "0":
            return {"error": result.get("msg1", "cancel failed"), "success": False}
        return {"success": True}
    except HTTPException:
        raise
    except Exception as e:
        return {"error": str(e), "success": False}


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
    values = _read_env_values()
    fields = []
    for field in ENV_FIELDS:
        key = field["key"]
        value = _virtual_env_value(key, values) if field.get("virtual") else values.get(key, "")
        item = {
            "key": key,
            "label": field["label"],
            "type": field["type"],
            "options": field.get("options", []),
            "hint": field.get("hint", ""),
            "secret": field["type"] == "secret",
            "virtual": bool(field.get("virtual")),
            "has_value": bool(value),
            "value": value,
            "masked": "",
        }
        fields.append(item)
    return {
        "path": str(ENV_PATH),
        "exists": ENV_PATH.exists(),
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
        _write_env_values(updates, ENV_PATH)
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
    _write_env_values(updates, ENV_PATH)
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


@app.get("/api/balance")
def get_balance():
    missing = _required_env_missing()
    if missing:
        if "KISTOCK_ACCOUNT_FORMAT" in missing:
            raise HTTPException(status_code=503, detail="KISTOCK_ACCOUNT must be 10 digits: 8-digit account number + 2-digit product code")
        raise HTTPException(status_code=503, detail=f"Missing environment variables: {', '.join(missing)}")

    try:
        api = _get_api()
        balance_data = _get_balance_data(api)
        parsed = _parse_balance(balance_data)
        for holding in parsed["holdings"]:
            holding.pop("_raw", None)
        if balance_data.get("_cache"):
            parsed["_cache"] = balance_data["_cache"]
        return parsed
    except SystemExit as e:
        raise HTTPException(status_code=502, detail=f"KIS API initialization failed: {e}") from e
    except KISAccountError as e:
        raise HTTPException(status_code=503, detail=f"KIS account setting is invalid. Check KISTOCK_ACCOUNT: {e}") from e
    except KISRateLimitError as e:
        raise HTTPException(status_code=429, detail=f"KIS API rate limit exceeded. Retry shortly: {e}") from e
    except RuntimeError as e:
        if "timed out" in str(e):
            raise HTTPException(status_code=504, detail=f"KIS balance API timed out after {BALANCE_FETCH_TIMEOUT_SECONDS:g}s") from e
        raise HTTPException(status_code=502, detail=f"KIS API request failed: {e}") from e
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"KIS API request failed: {e}") from e


from pydantic import BaseModel, Field

class NewStrategyPayload(BaseModel):
    name: str = Field(..., min_length=1)
    model: str = Field(..., min_length=1)
    weight: float = Field(..., ge=0.0, le=1.0)
    description: str = Field("")

class SelectStrategyPayload(BaseModel):
    selected: bool


@app.get("/api/ai-strategies")
def get_ai_strategies():
    from src.db.repository import load_ai_strategies
    return {"strategies": load_ai_strategies()}


@app.post("/api/ai-strategies")
def create_ai_strategy(payload: NewStrategyPayload):
    from src.db.repository import load_ai_strategies, save_ai_strategies
    import uuid
    import time
    
    strategies = load_ai_strategies()
    new_id = f"strategy_{int(time.time())}_{uuid.uuid4().hex[:6]}"
    new_strat = {
        "id": new_id,
        "name": payload.name,
        "provider": "openai" if payload.model != "none" else "none",
        "model": payload.model,
        "weight": payload.weight,
        "description": payload.description,
        "selected": False
    }
    strategies.append(new_strat)
    save_ai_strategies(strategies)
    return {"ok": True, "strategy": new_strat}


@app.post("/api/ai-strategies/{id}/select")
def select_ai_strategy(id: str, payload: SelectStrategyPayload):
    from src.db.repository import load_ai_strategies, save_ai_strategies
    
    strategies = load_ai_strategies()
    found = False
    for s in strategies:
        if s["id"] == id:
            s["selected"] = payload.selected
            found = True
            break
            
    if not found:
        raise HTTPException(status_code=404, detail="Strategy not found")
        
    save_ai_strategies(strategies)
    return {"ok": True}


@app.post("/api/ai-strategies/{id}/verify")
def verify_ai_strategy(id: str):
    from src.db.repository import load_ai_strategies
    strategies = load_ai_strategies()
    strategy = next((s for s in strategies if s["id"] == id), None)
    if not strategy:
        raise HTTPException(status_code=404, detail="Strategy not found")
        
    if strategy["provider"] == "none":
        return {"ok": True, "success": True, "speed_ms": 1, "message": "룰베이스 지표 점수제: 검증 불필요 (100% 로컬 연산)"}
        
    from src.strategy.predict import ModelPredictor
    import time
    
    predictor = ModelPredictor()
    predictor.enabled = True
    predictor.model_name = strategy["model"]
    
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
    
    start_time = time.time()
    try:
        prediction = predictor.predict(test_features)
        duration_ms = int((time.time() - start_time) * 1000)
        
        if prediction.get("fallback_reason") and not prediction.get("ml_score"):
            return {
                "ok": True,
                "success": False,
                "speed_ms": duration_ms,
                "message": f"API 검증 실패 (Fallback 감지): {prediction.get('fallback_reason')}"
            }
            
        return {
            "ok": True,
            "success": True,
            "speed_ms": duration_ms,
            "message": f"API 추론 검증 성공! 예상 점수: {prediction.get('final_score')}점 (ML 점수: {prediction.get('ml_score')})"
        }
    except Exception as ex:
        duration_ms = int((time.time() - start_time) * 1000)
        return {
            "ok": True,
            "success": False,
            "speed_ms": duration_ms,
            "message": f"추론 통신 에러: {type(ex).__name__} — {ex}"
        }


from typing import Optional

class WatchlistAddPayload(BaseModel):
    symbol: str = Field(..., min_length=6, max_length=6)

class WatchlistTogglePayload(BaseModel):
    enabled: bool
    threshold: Optional[float] = None

@app.get("/api/watchlist")
def get_watchlist():
    from src.db.repository import load_watchlist_data, get_watchlist_extra_info
    from src.strategy.seven_split import STOCK_NAMES
    data = load_watchlist_data()
    symbols_detail = []
    for code in data.get("symbols", []):
        extra = get_watchlist_extra_info(code)
        symbols_detail.append({
            "symbol": code,
            "name": STOCK_NAMES.get(code, "알 수 없는 종목"),
            "price": extra["price"],
            "score": extra["score"],
            "volume": extra["volume"],
            "reason": extra["reason"]
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


@app.post("/api/watchlist/scan-trigger")
async def trigger_watchlist_ai_scan():
    from src.db.repository import load_watchlist_data, save_watchlist_data
    from src.strategy.seven_split import sync_watchlist_runtime, STOCK_NAMES
    
    missing = _required_env_missing()
    if missing:
        raise HTTPException(status_code=503, detail=f"스캔 환경 변수가 미비합니다: {', '.join(missing)}")
        
    try:
        api = _get_api()
        parsed = _parse_balance(_get_balance_data(api))
        
        # GPT-5-mini 기반 강세 후보 실시간 AI 분석 가동
        ranker_model = "gpt-5-mini"
        ranker_weight = 0.4
        optimizer = "score_tilted_inverse_vol"
        
        payload = build_dashboard_candidates(
            api, parsed, min_score=1, ranker=ranker_model, ranker_weight=ranker_weight, optimizer=optimizer
        )
        
        added_symbols = []
        watchlist_data = load_watchlist_data()
        
        if payload["scanned"] > 0:
            needs_save = False
            threshold = watchlist_data.get("ai_auto_add_threshold", 3.0)
            for cand in payload["candidates"]:
                if cand.get("score", 0.0) >= threshold:
                    symbol = cand["ticker"]
                    if symbol not in watchlist_data["symbols"]:
                        watchlist_data["symbols"].append(symbol)
                        added_symbols.append({
                            "symbol": symbol,
                            "name": cand["name"],
                            "score": cand["score"]
                        })
                        needs_save = True
            if needs_save:
                save_watchlist_data(watchlist_data)
                sync_watchlist_runtime()
                
        return {
            "ok": True,
            "scanned": payload["scanned"],
            "added_count": len(added_symbols),
            "added_symbols": added_symbols
        }
    except Exception as e:
        logger.error(f"Failed to manually trigger watchlist AI scan: {e}")
        raise HTTPException(status_code=500, detail=f"AI 스캔 및 자동추가 실행 중 오류 발생: {str(e)}")


@app.get("/api/signals")
async def get_signals():
    missing = _required_env_missing()
    if missing:
        raise HTTPException(status_code=503, detail=f"Missing environment variables: {', '.join(missing)}")

    try:
        api = _get_api()
        parsed = _parse_balance(_get_balance_data(api))
        return {"signals": build_dashboard_signals(api, parsed)}
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Signal analysis failed: {e}") from e


@app.get("/api/candidates")
async def get_candidates(
    min_score: int = 2,
    ranker: str = "gpt_5_mini",
    optimizer: str = "score_tilted_inverse_vol",
):
    if min_score < 1:
        raise HTTPException(status_code=400, detail="min_score must be greater than 0")

    missing = _required_env_missing()
    if missing:
        raise HTTPException(status_code=503, detail=f"Missing environment variables: {', '.join(missing)}")

    if ranker == "gpt_5_mini" and optimizer == "score_tilted_inverse_vol":
        cached = _load_candidate_cache(min_score)
    else:
        cached = _load_candidate_cache(min_score, ranker, optimizer)
        
    if cached is not None:
        return cached

    try:
        api = _get_api()
        parsed = _parse_balance(_get_balance_data(api))
        
        from src.db.repository import load_ai_strategies
        strats = load_ai_strategies()
        selected_strat = next((s for s in strats if s["id"] == ranker), None)
        
        if selected_strat:
            ranker_model = selected_strat["model"]
            ranker_weight = selected_strat["weight"]
            if selected_strat["provider"] == "none":
                ranker_model = "none"
        else:
            ranker_model = ranker
            ranker_weight = 0.4
            
        payload = build_dashboard_candidates(
            api, parsed, min_score=min_score, ranker=ranker_model, ranker_weight=ranker_weight, optimizer=optimizer
        )
        
        if payload["scanned"] > 0:
            if ranker == "gpt_5_mini" and optimizer == "score_tilted_inverse_vol":
                _save_candidate_cache(
                    min_score, payload["candidates"], payload["scan_summary"], payload["scanned"]
                )
            else:
                _save_candidate_cache(
                    min_score, payload["candidates"], payload["scan_summary"], payload["scanned"], ranker, optimizer
                )
            # Automatically save scan results to DB for history tracking
            from src.db.repository import save_scanned_candidate
            for cand in payload["candidates"]:
                save_scanned_candidate(
                    symbol=cand["ticker"],
                    name=cand["name"],
                    score=cand["score"],
                    reasons=cand["reasons"],
                    price=cand["current_price"],
                    env=trader.TRADING_ENV,
                    indicators={
                        "rsi": cand.get("rsi"),
                        "rsi2": cand.get("rsi2"),
                        "macd_hist": cand.get("macd_hist"),
                        "sma20": cand.get("sma20"),
                        "sma60": cand.get("sma60"),
                    }
                )
            
            # AI 자동 추가적용 로직
            from src.db.repository import load_watchlist_data, save_watchlist_data
            from src.strategy.seven_split import sync_watchlist_runtime
            try:
                watchlist_data = load_watchlist_data()
                if watchlist_data.get("ai_auto_add", False):
                    needs_save = False
                    threshold = watchlist_data.get("ai_auto_add_threshold", 3.0)
                    for cand in payload["candidates"]:
                        if cand.get("score", 0.0) >= threshold:
                            symbol = cand["ticker"]
                            if symbol not in watchlist_data["symbols"]:
                                watchlist_data["symbols"].append(symbol)
                                needs_save = True
                    if needs_save:
                        save_watchlist_data(watchlist_data)
                        sync_watchlist_runtime()
            except Exception as w_err:
                logger.warning(f"Failed to auto-add high score candidate to watchlist: {w_err}")
                
        return payload
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Candidate scan failed: {e}") from e


@app.get("/api/candidates/history")
async def get_candidates_history(limit: int = 100, days: int = 30):
    try:
        from src.db.repository import get_scanned_candidates_history
        history = get_scanned_candidates_history(limit=limit, days=days)
        return {"history": history}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/candidates/history/{candidate_id}")
async def delete_candidate_history(candidate_id: int):
    try:
        from src.db.repository import delete_scanned_candidate
        deleted_count = delete_scanned_candidate(candidate_id)
        if deleted_count <= 0:
            raise HTTPException(status_code=404, detail="Candidate not found")
        return {"ok": True, "deleted_count": deleted_count}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/execution-plan")
async def get_execution_plan():
    missing = _required_env_missing()
    if missing:
        raise HTTPException(status_code=503, detail=f"Missing environment variables: {', '.join(missing)}")
    try:
        return build_dashboard_execution_plan()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Execution plan failed: {e}") from e


@app.get("/api/ai-allocation")
def get_ai_allocation():
    missing = _required_env_missing()
    if missing:
        raise HTTPException(status_code=503, detail=f"Missing environment variables: {', '.join(missing)}")

    try:
        api = _get_api()
        parsed = _parse_balance(_get_balance_data(api))
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
        return trader.generate_ai_weight_plan(holdings, parsed["total_eval"])
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"AI allocation failed: {e}") from e


def _holding_history(api: KIStockAPI, parsed: dict, n: int = 120) -> list[dict]:
    holdings = []
    for holding in parsed["holdings"]:
        daily = api.get_daily(holding["symbol"], n=n)
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
    return holdings


@app.get("/api/portfolio-optimizer")
def get_portfolio_optimizer():
    missing = _required_env_missing()
    if missing:
        raise HTTPException(status_code=503, detail=f"Missing environment variables: {', '.join(missing)}")

    try:
        api = _get_api()
        parsed = _parse_balance(_get_balance_data(api))
        holdings = _holding_history(api, parsed, n=120)
        return trader.generate_portfolio_optimizer_plan(holdings, parsed["total_eval"])
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Portfolio optimizer failed: {e}") from e


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
    now = trader.datetime.now(trader.KST).strftime("%Y-%m-%d %H:%M:%S")

    _init_approval_db()
    with trader.connect_db() as conn:
        cursor = conn.execute(
            """
            INSERT INTO approvals
            (created_at, updated_at, symbol, name, action, qty, price, reason, source, status, response_msg)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', '')
            """,
            (now, now, symbol, name, action, qty, price, reason, source),
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


def _load_pending_approval(approval_id: int) -> dict:
    item = _approval_by_id(approval_id)
    if not item:
        raise HTTPException(status_code=404, detail="approval not found")
    if item["status"] != "pending":
        raise HTTPException(status_code=409, detail=f"approval is already {item['status']}")
    return item


def _claim_pending_approval(approval_id: int) -> dict:
    item = _load_pending_approval(approval_id)
    now = trader.datetime.now(trader.KST).strftime("%Y-%m-%d %H:%M:%S")
    with trader.connect_db() as conn:
        cursor = conn.execute(
            """
            UPDATE approvals
            SET status = 'executing', response_msg = 'Submitting order to broker', updated_at = ?
            WHERE id = ? AND status = 'pending'
            """,
            (now, approval_id),
        )
    if cursor.rowcount != 1:
        current = _approval_by_id(approval_id)
        if current is None:
            raise HTTPException(status_code=404, detail="approval not found")
        raise HTTPException(status_code=409, detail=f"approval is already {current['status']}")
    return item


def _approval_response_msg(result: dict, *, ok: bool) -> str:
    response_msg = str(result.get("msg1", ""))
    if ok and not trader.DRY_RUN and trader.TRADING_ENV == "demo":
        response_msg = f"{response_msg} (KIS demo order submitted; confirm fill status in broker order history)"
    return response_msg


def _current_holding_qty_from_balance(api, symbol: str) -> int:
    try:
        parsed = _parse_balance(_get_balance_data(api, allow_cache=False))
    except Exception:
        return 0
    for holding in parsed.get("holdings", []):
        if str(holding.get("symbol") or "") == str(symbol):
            return _to_int(holding.get("qty"))
    return 0


def _pending_approval_ids(limit: int = 200) -> list[int]:
    _init_approval_db()
    with trader.connect_db() as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT id FROM approvals WHERE status = 'pending' ORDER BY id ASC LIMIT ?",
            (limit,),
        ).fetchall()
    return [int(row["id"]) for row in rows]


def _auto_approve_pending_approvals(limit: int = 200) -> list[dict]:
    results = []
    for approval_id in _pending_approval_ids(limit):
        try:
            results.append(_approve_pending_approval(approval_id, "자동승인"))
        except HTTPException:
            continue
    return results


def _approve_pending_approval(approval_id: int, approval_label: str = "수동승인") -> dict:
    item = _claim_pending_approval(approval_id)
    result: dict = {}
    try:
        api = _get_api()
        pre_order_qty = _current_holding_qty_from_balance(api, item["symbol"])
        result = api.place_order(item["symbol"], item["action"], item["price"], item["qty"])
        ok = result.get("rt_cd") == "0"
        status = "executed" if ok else "failed"
        response_msg = _approval_response_msg(result, ok=ok)
        if False:  # legacy non-English broker note disabled
            response_msg = f"{response_msg} (二쇰Ц?묒닔 ?꾨즺 - ?ㅼ젣 泥닿껐 ?щ???HTS/MTS?먯꽌 ?뺤씤 ?붾쭩)"
        trader.save_trade(
            item["symbol"],
            item["name"],
            item["action"],
            item["qty"],
            item["price"],
            item["reason"],
            ok,
            trader.ORDER_SUBMISSION_ENABLED,
            broker_result=result,
            order_status="submitted" if ok and trader.ORDER_SUBMISSION_ENABLED else "simulated" if ok else "failed",
            response_msg=response_msg,
            filled_qty=0 if ok and trader.ORDER_SUBMISSION_ENABLED else item["qty"] if ok else 0,
            filled_price=0 if ok and trader.ORDER_SUBMISSION_ENABLED else item["price"] if ok else 0,
            pre_order_qty=pre_order_qty,
        )
    except Exception as e:
        status = "failed"
        response_msg = str(e)

    now = trader.datetime.now(trader.KST).strftime("%Y-%m-%d %H:%M:%S")
    with trader.connect_db() as conn:
        conn.execute(
            "UPDATE approvals SET status = ?, response_msg = ?, updated_at = ? WHERE id = ?",
            (status, response_msg, now, approval_id),
        )

    # Slack 알림
    try:
        indicators = {"rsi": "-", "sma20": 0, "sma60": 0, "rt": 0}
        _slack_order(
            item["name"], item["symbol"], item["action"],
            item["qty"], item["price"],
            f"[대시보드 {approval_label}] {item.get('reason', '')}",
            status == "executed",
            indicators,
        )
    except Exception:
        pass

    return {"id": approval_id, "status": status, "response_msg": response_msg}


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


import time

_cloud_trades_cache = None
_cloud_trades_cache_time = 0

def fetch_cloud_trades():
    global _cloud_trades_cache, _cloud_trades_cache_time
    if _cloud_trades_cache is not None and time.time() - _cloud_trades_cache_time < 10:
        return [dict(t) for t in _cloud_trades_cache]
        
    try:
        subprocess.run(
            ["git", "fetch", "origin", "database:database"],
            check=False,
            capture_output=True,
            timeout=GIT_FETCH_TIMEOUT_SECONDS,
        )
        output = subprocess.check_output(
            ["git", "show", "origin/database:trades.json"],
            stderr=subprocess.STDOUT,
            timeout=GIT_FETCH_TIMEOUT_SECONDS,
        ).decode("utf-8")
        trades = json.loads(output)
        
        _cloud_trades_cache = trades
        _cloud_trades_cache_time = time.time()
        return [dict(t) for t in trades]
    except Exception as e:
        if _cloud_trades_cache is not None:
            return [dict(t) for t in _cloud_trades_cache]
        return []


def _load_merged_trades() -> list[dict]:
    cloud_trades = fetch_cloud_trades() or []
    local_trades = []
    with trader.connect_db() as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM trades ORDER BY ts ASC").fetchall()
        local_trades = [dict(row) for row in rows]

    merged_trades = {}
    for t in cloud_trades + local_trades:
        ts = t.get("ts") or t.get("timestamp")
        if not ts:
            continue
        key = f"{ts}_{t.get('symbol')}_{t.get('action')}"
        merged_trades[key] = {
            "ts": ts,
            "symbol": t.get("symbol"),
            "name": t.get("name", t.get("symbol")),
            "action": t.get("action"),
            "qty": _to_int(t.get("qty")),
            "price": _to_int(t.get("price")),
            "reason": t.get("reason", ""),
            "ok": t.get("ok", 1),
            "env": t.get("env", "demo"),
            "dry_run": t.get("dry_run", 0),
            "broker_order_id": t.get("broker_order_id", ""),
            "order_status": t.get("order_status", ""),
            "filled_qty": _to_int(t.get("filled_qty")),
            "filled_price": _to_int(t.get("filled_price")),
            "response_msg": t.get("response_msg", ""),
        }
    return sorted(merged_trades.values(), key=lambda x: x["ts"])


def _trade_is_ok(trade: dict) -> bool:
    return bool(_to_int(trade.get("ok"), 1))


def _trade_is_dry_run(trade: dict) -> bool:
    return bool(_to_int(trade.get("dry_run"), 0))


def _trade_is_sync_adjustment(trade: dict) -> bool:
    reason = str(trade.get("reason") or "").lower()
    return any(token in reason for token in ("sync", "adjust"))


def _account_trades(trades: list[dict]) -> list[dict]:
    account_rows = []
    # If the trader is running in dry-run/demo mode, or if there are no live trades, show dry-run trades
    show_dry_run = trader.DRY_RUN or (trader.TRADING_ENV == "demo")
    
    for trade in trades:
        if not _trade_is_ok(trade):
            continue
        if _trade_is_sync_adjustment(trade):
            continue
        if not show_dry_run and _trade_is_dry_run(trade):
            continue
            
        order_status = str(trade.get("order_status") or "")
        filled_qty = _to_int(trade.get("filled_qty"))
        filled_price = _to_int(trade.get("filled_price"))
        if order_status in {"submitted", "partial", "open"} and filled_qty <= 0:
            continue
        if filled_qty > 0:
            trade = {**trade, "qty": filled_qty, "price": filled_price or _to_int(trade.get("price"))}
        account_rows.append(trade)
    return account_rows


def _period_bucket() -> dict:
    return {
        "order_count": 0,
        "buy_count": 0,
        "sell_count": 0,
        "buy_amount": 0,
        "sell_amount": 0,
        "realized_pnl": 0,
        "cost_of_sold": 0,
        "realized_pnl_rate": 0.0,
        "net_cashflow": 0,
    }


def _build_periodic_performance(trades: list[dict]) -> dict:
    daily: dict[str, dict] = {}
    monthly: dict[str, dict] = {}
    holdings: dict[str, dict] = {}

    for trade in _account_trades(trades):
        ts = str(trade.get("ts") or "")
        if len(ts) < 10 or ts[0] == "-":
            continue

        day_key = ts[:10]
        month_key = ts[:7]
        action = str(trade.get("action") or "").lower()
        symbol = str(trade.get("symbol") or "")
        qty = _to_int(trade.get("qty"))
        price = _to_int(trade.get("price"))
        amount = qty * price

        if qty <= 0 or price <= 0 or action not in {"buy", "sell"}:
            continue

        day = daily.setdefault(day_key, _period_bucket())
        month = monthly.setdefault(month_key, _period_bucket())
        for bucket in (day, month):
            bucket["order_count"] += 1
            if action == "buy":
                bucket["buy_count"] += 1
                bucket["buy_amount"] += amount
            else:
                bucket["sell_count"] += 1
                bucket["sell_amount"] += amount

        if symbol not in holdings:
            holdings[symbol] = {"qty": 0, "avg_cost": 0.0}
        holding = holdings[symbol]

        if action == "buy":
            total_qty = holding["qty"] + qty
            total_cost = holding["qty"] * holding["avg_cost"] + amount
            holding["qty"] = total_qty
            holding["avg_cost"] = total_cost / total_qty if total_qty > 0 else 0.0
        else:
            sell_qty = min(qty, holding["qty"])
            cost_of_shares_sold = int(holding["avg_cost"] * sell_qty)
            realized = int((price - holding["avg_cost"]) * sell_qty)
            
            day["realized_pnl"] += realized
            month["realized_pnl"] += realized
            day["cost_of_sold"] += cost_of_shares_sold
            month["cost_of_sold"] += cost_of_shares_sold
            
            holding["qty"] = max(0, holding["qty"] - sell_qty)
            if holding["qty"] <= 0:
                holding["avg_cost"] = 0.0

    for rows in (daily, monthly):
        for bucket in rows.values():
            bucket["net_cashflow"] = bucket["sell_amount"] - bucket["buy_amount"]
            bucket["realized_pnl_rate"] = round((bucket["realized_pnl"] / bucket["cost_of_sold"] * 100), 2) if bucket["cost_of_sold"] > 0 else 0.0

    return {
        "daily": [{"period": key, **value} for key, value in sorted(daily.items())],
        "monthly": [{"period": key, **value} for key, value in sorted(monthly.items())],
    }


def _broker_order_id_from_history(row: dict) -> str:
    for key in ("ODNO", "odno", "ord_no", "order_no"):
        value = row.get(key)
        if value:
            return str(value).strip()
    return ""


def _history_int(row: dict, *keys: str) -> int:
    for key in keys:
        value = row.get(key)
        parsed = _to_int(value)
        if parsed:
            return parsed
    return 0


def _history_fill_price(row: dict) -> int:
    return _history_int(
        row,
        "avg_prvs",
        "avg_pric",
        "avg_ccld_pric",
        "ccld_unpr",
        "ord_unpr",
    )


def _history_fill_qty(row: dict) -> int:
    return _history_int(row, "tot_ccld_qty", "ccld_qty", "cnqn", "ord_qty")


def _order_history_window(days: int = 7) -> tuple[str, str]:
    end = trader.datetime.now(trader.KST)
    start = end - trader.timedelta(days=max(1, days))
    return start.strftime("%Y%m%d"), end.strftime("%Y%m%d")


def _load_trackable_order_trades() -> list[dict]:
    trader.init_db()
    with trader.connect_db() as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT *
            FROM trades
            WHERE broker_order_id IS NOT NULL
              AND broker_order_id != ''
              AND COALESCE(order_status, '') IN ('submitted', 'partial', 'open')
            ORDER BY ts ASC
            """
        ).fetchall()
    return [dict(row) for row in rows]


def _sync_order_status_from_history(api, *, days: int = 7) -> dict:
    tracked = _load_trackable_order_trades()
    if not tracked:
        return {"ok": True, "checked_count": 0, "updated_count": 0, "orders": []}

    start_date, end_date = _order_history_window(days)
    try:
        history = api.get_trade_history(start_date, end_date)
    except Exception as exc:
        fallback = _sync_order_status_from_balance(api, tracked, reason=str(exc))
        return {
            **fallback,
            "ok": fallback.get("updated_count", 0) > 0,
            "history_error": str(exc),
            "history_count": 0,
            "fallback": "balance",
        }
    history_by_order_id = {
        order_id: row
        for row in history
        if (order_id := _broker_order_id_from_history(row))
    }

    orders = []
    updated_count = 0
    for trade in tracked:
        order_id = str(trade.get("broker_order_id") or "")
        row = history_by_order_id.get(order_id)
        if row is None:
            orders.append({"broker_order_id": order_id, "order_status": trade.get("order_status") or "submitted"})
            continue

        requested_qty = _to_int(trade.get("qty"))
        filled_qty = _history_fill_qty(row)
        filled_price = _history_fill_price(row)
        if filled_qty <= 0:
            order_status = "open"
        elif requested_qty > 0 and filled_qty < requested_qty:
            order_status = "partial"
        else:
            order_status = "filled"
        response_msg = f"KIS order history sync: {order_status}"
        updated_count += trader.update_trade_order_status(
            order_id,
            order_status=order_status,
            filled_qty=filled_qty,
            filled_price=filled_price,
            response_msg=response_msg,
            broker_result=row,
        )
        orders.append({
            "broker_order_id": order_id,
            "order_status": order_status,
            "filled_qty": filled_qty,
            "filled_price": filled_price,
        })

    return {
        "ok": True,
        "checked_count": len(tracked),
        "updated_count": updated_count,
        "history_count": len(history),
        "orders": orders,
    }


def _sync_order_status_from_balance(api, tracked: list[dict], *, reason: str = "") -> dict:
    try:
        parsed = _parse_balance(_get_balance_data(api, allow_cache=False))
    except Exception as exc:
        return {
            "ok": False,
            "checked_count": len(tracked),
            "updated_count": 0,
            "orders": [],
            "balance_error": str(exc),
            "history_error": reason,
        }

    holdings = {str(item.get("symbol") or ""): item for item in parsed.get("holdings", [])}
    orders = []
    updated_count = 0
    for trade in tracked:
        order_id = str(trade.get("broker_order_id") or "")
        symbol = str(trade.get("symbol") or "")
        action = str(trade.get("action") or "").lower()
        requested_qty = _to_int(trade.get("qty"))
        pre_order_qty = _to_int(trade.get("pre_order_qty"))
        current = holdings.get(symbol, {})
        current_qty = _to_int(current.get("qty"))
        current_price = _to_int(current.get("price")) or _to_int(trade.get("price"))

        filled = False
        if action == "buy" and requested_qty > 0:
            filled = current_qty >= pre_order_qty + requested_qty
        elif action == "sell" and requested_qty > 0:
            filled = current_qty <= max(0, pre_order_qty - requested_qty)

        if not filled:
            orders.append({
                "broker_order_id": order_id,
                "order_status": trade.get("order_status") or "submitted",
                "balance_confirmed": False,
            })
            continue

        response_msg = "Balance fallback sync: filled"
        updated_count += trader.update_trade_order_status(
            order_id,
            order_status="filled",
            filled_qty=requested_qty,
            filled_price=current_price,
            response_msg=response_msg,
            broker_result={
                "fallback": "balance",
                "history_error": reason,
                "pre_order_qty": pre_order_qty,
                "current_qty": current_qty,
            },
        )
        orders.append({
            "broker_order_id": order_id,
            "order_status": "filled",
            "filled_qty": requested_qty,
            "filled_price": current_price,
            "balance_confirmed": True,
        })

    return {
        "ok": True,
        "checked_count": len(tracked),
        "updated_count": updated_count,
        "orders": orders,
    }


@app.post("/api/trades/order-status/sync")
def sync_trade_order_status(days: int = 7):
    if trader.DRY_RUN:
        raise HTTPException(status_code=400, detail="Order status sync requires DRY_RUN=false")
    try:
        return _sync_order_status_from_history(_get_api(), days=days)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.post("/api/trades/sync")
def sync_trades():
    if trader.DRY_RUN:
        raise HTTPException(status_code=400, detail="紐⑥쓽 ?ㅽ뻾(DRY_RUN) 紐⑤뱶?먯꽌??利앷텒??怨꾩쥖 ?숆린?붾? ?ъ슜?????놁뒿?덈떎.")
    try:
        api = _get_api()
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
                
        return {"ok": True, "synced_count": synced_count}
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
        cloud_trades = fetch_cloud_trades() or []
        local_trades = []
        with trader.connect_db() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("SELECT * FROM trades ORDER BY ts ASC").fetchall()
            local_trades = [dict(row) for row in rows]
            
        # Merge cloud and local trades
        # Use a dictionary keyed by timestamp and symbol to deduplicate
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
                "dry_run": t.get("dry_run", 0)
            }
            
        trades = _account_trades(sorted(merged_trades.values(), key=lambda x: x["ts"]))
        
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
    try:
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
            "halted": loss_pct >= max_daily_loss or Path(".runtime/kill_switch.json").exists()
        }
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


# =============================================================================
# Executor 상태 (스위치) API
# =============================================================================

@app.get("/api/futures-signals/executor/state")
async def get_executor_state():
    """실행 상태 조회 (스위치 ON/OFF 현황)"""
    from src.futures_signals.executor import get_executor
    from dataclasses import asdict
    executor = get_executor()
    return asdict(executor.state)


@app.put("/api/futures-signals/executor/state")
async def update_executor_state(request: Request):
    """스위치 ON/OFF 변경"""
    from src.futures_signals.executor import get_executor
    from dataclasses import asdict
    body = await request.json()
    executor = get_executor()
    executor.update_state(**body)
    return {"ok": True, "state": asdict(executor.state)}


# =============================================================================
# 성과 조회 API
# =============================================================================

@app.get("/api/futures-signals/performance/mock")
async def get_mock_performance():
    """Mock 시뮬레이터 성과"""
    from src.futures_signals.executor import get_executor
    executor = get_executor()
    return executor.get_mock_performance()


@app.get("/api/futures-signals/performance/paper")
async def get_paper_performance():
    """KIS 모의계좌 성과"""
    try:
        from src.api.kis_futures_api import KISFuturesAPI
        api = KISFuturesAPI(demo=True)
        if not api._configured:
            return {"status": "not_configured", "demo": True}
        balance = api.get_balance()
        positions = api.get_positions()
        executions = api.get_executions()
        return {
            "balance": balance,
            "positions": positions,
            "executions": executions,
            "demo": True,
        }
    except Exception as e:
        return {"status": "error", "message": str(e), "demo": True}


@app.get("/api/futures-signals/performance/live")
async def get_live_performance():
    """KIS 실계좌 성과"""
    try:
        from src.futures_signals.executor import get_executor
        executor = get_executor()
        if not executor.state.live_trading_enabled:
            return {"status": "disabled", "message": "실계좌 거래가 비활성화 상태입니다"}
        from src.api.kis_futures_api import KISFuturesAPI
        api = KISFuturesAPI(demo=False)
        balance = api.get_balance()
        positions = api.get_positions()
        return {
            "balance": balance,
            "positions": positions,
            "demo": False,
        }
    except Exception as e:
        return {"status": "error", "message": str(e), "demo": False}


# =============================================================================
# Telegram 단계별 인증 API
# =============================================================================

# Telegram 인증 상태 저장 (메모리)
_telegram_auth_state: dict = {"step": "idle", "phone_code_hash": None}


@app.post("/api/futures-signals/collector/auth/start")
async def telegram_auth_start(request: Request):
    """
    Telegram 인증 1단계: 전화번호로 SMS 코드 발송
    body: {"phone": "+821012345678"}
    """
    global _telegram_auth_state
    body = await request.json()
    phone = body.get("phone", "")

    try:
        from telethon import TelegramClient
    except ImportError:
        return {"ok": False, "error": "telethon not installed"}

    try:
        from src.config import config as _cfg
        api_id = int(_cfg.telegram_api_id or 0) if hasattr(_cfg, "telegram_api_id") else int(os.environ.get("TELEGRAM_API_ID", "0") or "0")
        api_hash = (_cfg.telegram_api_hash or "") if hasattr(_cfg, "telegram_api_hash") else (os.environ.get("TELEGRAM_API_HASH", "") or "")
        session_path = str(Path(".runtime/telegram_session"))

        if not api_id or not api_hash:
            return {"ok": False, "error": "TELEGRAM_API_ID 또는 TELEGRAM_API_HASH가 설정되지 않았습니다"}

        client = TelegramClient(session_path, api_id, api_hash)
        await client.connect()
        result = await client.send_code_request(phone)
        _telegram_auth_state = {
            "step": "code_sent",
            "phone": phone,
            "phone_code_hash": result.phone_code_hash,
        }
        await client.disconnect()
        return {"ok": True, "message": f"{phone}으로 인증 코드가 발송되었습니다"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@app.post("/api/futures-signals/collector/auth/verify")
async def telegram_auth_verify(request: Request):
    """
    Telegram 인증 2단계: SMS 코드 입력으로 세션 생성
    body: {"code": "12345"}
    """
    global _telegram_auth_state
    body = await request.json()
    code = body.get("code", "")

    if _telegram_auth_state.get("step") != "code_sent":
        return {"ok": False, "error": "먼저 인증 코드를 발송해주세요"}

    try:
        from telethon import TelegramClient
    except ImportError:
        return {"ok": False, "error": "telethon not installed"}

    try:
        from src.config import config as _cfg
        api_id = int(_cfg.telegram_api_id or 0) if hasattr(_cfg, "telegram_api_id") else int(os.environ.get("TELEGRAM_API_ID", "0") or "0")
        api_hash = (_cfg.telegram_api_hash or "") if hasattr(_cfg, "telegram_api_hash") else (os.environ.get("TELEGRAM_API_HASH", "") or "")
        session_path = str(Path(".runtime/telegram_session"))
        phone = _telegram_auth_state["phone"]
        phone_code_hash = _telegram_auth_state["phone_code_hash"]

        client = TelegramClient(session_path, api_id, api_hash)
        await client.connect()
        await client.sign_in(phone, code, phone_code_hash=phone_code_hash)
        await client.disconnect()

        _telegram_auth_state = {"step": "authenticated"}
        return {"ok": True, "message": "Telegram 인증이 완료되었습니다. 서버를 재시작하거나 폴링을 수동으로 시작하세요."}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@app.get("/api/usage/quota")
def get_antigravity_quota_api():
    import subprocess
    import re
    
    try:
        res = subprocess.run(
            ["antigravity-usage", "quota"],
            capture_output=True,
            text=True,
            shell=True,
            timeout=12
        )
        if res.returncode != 0:
            logger.warning(f"antigravity-usage quota CLI failed with code {res.returncode}: {res.stderr}")
            return {"ok": False, "error": "CLI 실행에 실패했습니다. (로그인 필요)"}
            
        stdout = res.stdout
        
        email = "Unknown"
        email_match = re.search(r"👤\s*(\S+@\S+)", stdout)
        if email_match:
            email = email_match.group(1).strip()
            
        quota_list = []
        lines = stdout.splitlines()
        for line in lines:
            if "│" in line and "Model" not in line and "┌" not in line and "├" not in line and "└" not in line:
                parts = [p.strip() for p in line.split("│") if p.strip()]
                if len(parts) >= 2:
                    model = parts[0]
                    remaining = parts[1]
                    resets = parts[2] if len(parts) >= 3 else ""
                    remaining_clean = remaining.replace("🟢", "").replace("🟡", "").replace("🔴", "").strip()
                    quota_list.append({
                        "model": model,
                        "remaining": remaining_clean,
                        "resets_in": resets
                    })
                    
        return {
            "ok": True,
            "email": email,
            "quota": quota_list,
            "raw_text": stdout.strip()
        }
    except Exception as e:
        logger.error(f"Failed to fetch antigravity quota: {e}")
        return {"ok": False, "error": str(e)}


# ----------------------------------------------------
# Scheduler Run and Status Management APIs
# ----------------------------------------------------

_scheduler_running_lock = threading.Lock()
_scheduler_run_state = {
    "is_running": False,
    "mode": None,
    "started_at": None,
    "completed_at": None,
    "result": None,
    "error": None
}

def _bg_run_scheduled_cycle(mode: str, include_ai_rebalance: bool, auto_approve: bool):
    global _scheduler_run_state
    try:
        from src.scheduler import run_scheduled_cycle
        result = run_scheduled_cycle(
            mode=mode,
            include_ai_rebalance=include_ai_rebalance,
            auto_approve=auto_approve
        )
        with _scheduler_running_lock:
            _scheduler_run_state["is_running"] = False
            _scheduler_run_state["completed_at"] = trader.datetime.now(trader.KST).isoformat()
            _scheduler_run_state["result"] = result
            _scheduler_run_state["error"] = None
    except Exception as e:
        with _scheduler_running_lock:
            _scheduler_run_state["is_running"] = False
            _scheduler_run_state["completed_at"] = trader.datetime.now(trader.KST).isoformat()
            _scheduler_run_state["result"] = None
            _scheduler_run_state["error"] = str(e)


@app.get("/api/scheduler/status")
def get_scheduler_status():
    global _scheduler_run_state
    
    config = {
        "cron_tz": os.environ.get("HANSTOCK_CRON_TZ", "Asia/Seoul"),
        "daily_auto_retries": os.environ.get("HANSTOCK_DAILY_AUTO_RETRIES", "3"),
        "scheduler_retries": os.environ.get("HANSTOCK_SCHEDULER_RETRIES", "1"),
        "slack_enabled": os.environ.get("HANSTOCK_SCHEDULER_SLACK", "true"),
        "sync_enabled": os.environ.get("HANSTOCK_ORDER_STATUS_SYNC", "true"),
        "result_path": os.environ.get("HANSTOCK_SCHEDULER_RESULT_PATH", ".runtime/daily_auto_last_result.json"),
        "trading_env": trader.TRADING_ENV,
        "dry_run": trader.DRY_RUN,
        "order_submission": trader.ORDER_SUBMISSION_ENABLED,
    }
    
    last_result = None
    try:
        from src.db.repository import load_latest_scheduler_result
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
            
    return {
        "config": config,
        "last_result": last_result,
        "run_state": _scheduler_run_state
    }


@app.post("/api/scheduler/run")
def trigger_scheduler_run(payload: dict = Body(...)):
    global _scheduler_run_state
    mode = str(payload.get("mode", "daily_auto")).lower()
    if mode not in {"daily_auto", "execute", "analysis_only"}:
        raise HTTPException(status_code=400, detail="Invalid scheduler mode")
        
    include_ai_rebalance = bool(payload.get("include_ai_rebalance", True))
    auto_approve = bool(payload.get("auto_approve", mode == "daily_auto"))
    
    with _scheduler_running_lock:
        if _scheduler_run_state["is_running"]:
            raise HTTPException(status_code=409, detail="스케줄러가 이미 실행 중입니다.")
        
        _scheduler_run_state["is_running"] = True
        _scheduler_run_state["mode"] = mode
        _scheduler_run_state["started_at"] = trader.datetime.now(trader.KST).isoformat()
        _scheduler_run_state["completed_at"] = None
        _scheduler_run_state["result"] = None
        _scheduler_run_state["error"] = None
        
    t = threading.Thread(
        target=_bg_run_scheduled_cycle,
        args=(mode, include_ai_rebalance, auto_approve),
        daemon=True
    )
    t.start()
    return {"status": "started", "mode": mode}

