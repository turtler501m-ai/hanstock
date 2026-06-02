from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional
from dotenv import load_dotenv


load_dotenv(override=True)

class Settings(BaseSettings):
    # KIS API Credentials (국내주식)
    kistock_app_key: str = ""
    kistock_app_secret: str = ""
    kistock_account: str = ""
    kistock_hts_id: str = ""

    # KIS 해외선물 모의계좌
    kis_futures_demo_app_key: Optional[str] = None
    kis_futures_demo_app_secret: Optional[str] = None
    kis_futures_demo_account: Optional[str] = None

    # KIS 해외선물 실계좌
    kis_futures_real_app_key: Optional[str] = None
    kis_futures_real_app_secret: Optional[str] = None
    kis_futures_real_account: Optional[str] = None

    # Telegram
    telegram_api_id: Optional[str] = None
    telegram_api_hash: Optional[str] = None
    telegram_target_channels: Optional[str] = None

    # Notifications
    slack_webhook_url: Optional[str] = ""
    
    # Trading Modes
    trading_env: str = "demo"
    dry_run: bool = True
    enable_live_trading: bool = False
    require_approval: bool = True
    
    # Strategy Params
    split_n: int = 7
    stop_loss_pct: float = -15.0
    take_profit: float = 30.0
    rsi_buy: int = 30
    rsi_sell: int = 70
    
    # Risk Management
    total_capital: float = 10000000.0
    max_positions: int = 3
    max_single_weight: float = 0.30
    cash_buffer: float = 0.20
    max_daily_loss_pct: float = 3.0
    
    # Others
    scan_universe_size: int = 50
    yfinance_timeout_seconds: int = 8
    kis_circuit_cooldown_seconds: int = 60
    trade_db_path: str = ".runtime/trades.sqlite"
    log_file: str = "logs/trader.log"
    active_model_version: str = "v1"
    ai_strategy_enabled: bool = False
    ai_score_weight: float = 0.40
    ai_min_model_confidence: float = 0.60
    ai_require_backtest_pass: bool = True
    ai_auto_approve: bool = False
    openai_api_key: str = ""
    openai_model: str = "gpt-5-mini"
    openai_timeout_seconds: float = 20.0
    ai_candidate_limit: int = 5

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

config = Settings()
