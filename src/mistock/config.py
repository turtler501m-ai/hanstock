from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class MistockConfig:
    market: str = os.environ.get("MISTOCK_MARKET", "NASDAQ")
    trading_env: str = os.environ.get("MISTOCK_TRADING_ENV", "paper")
    dry_run: bool = os.environ.get("MISTOCK_DRY_RUN", "true").lower() in {"1", "true", "yes", "on"}
    enable_live_trading: bool = os.environ.get("MISTOCK_ENABLE_LIVE_TRADING", "false").lower() in {"1", "true", "yes", "on"}
    require_approval: bool = os.environ.get("MISTOCK_REQUIRE_APPROVAL", "true").lower() in {"1", "true", "yes", "on"}
    total_capital: float = float(os.environ.get("MISTOCK_TOTAL_CAPITAL", "100000"))
    cash_buffer: float = float(os.environ.get("MISTOCK_CASH_BUFFER", "0.20"))
    max_positions: int = int(os.environ.get("MISTOCK_MAX_POSITIONS", "5"))
    max_single_weight: float = float(os.environ.get("MISTOCK_MAX_SINGLE_WEIGHT", "0.25"))
    max_daily_loss_pct: float = float(os.environ.get("MISTOCK_MAX_DAILY_LOSS_PCT", "3.0"))
    split_n: int = int(os.environ.get("MISTOCK_SPLIT_N", "7"))
    stop_loss_pct: float = float(os.environ.get("MISTOCK_STOP_LOSS_PCT", "-12"))
    take_profit: float = float(os.environ.get("MISTOCK_TAKE_PROFIT", "25"))
    rsi_buy: int = int(os.environ.get("MISTOCK_RSI_BUY", "35"))
    rsi_sell: int = int(os.environ.get("MISTOCK_RSI_SELL", "72"))
    scan_universe_size: int = int(os.environ.get("MISTOCK_SCAN_UNIVERSE_SIZE", "60"))
    yfinance_timeout_seconds: int = int(os.environ.get("MISTOCK_YFINANCE_TIMEOUT_SECONDS", "10"))
    currency: str = os.environ.get("MISTOCK_CURRENCY", "USD")
    trade_db_path: Path = Path(os.environ.get("MISTOCK_TRADE_DB_PATH", ".runtime/mistock/trades.sqlite"))


config = MistockConfig()

