import sqlite3
import os
import json
from pathlib import Path
from datetime import datetime, timedelta, timezone
from src.config import config
from src.utils.logger import logger

KST = timezone(timedelta(hours=9))

class DBWrapper:
    def __init__(self, conn, is_pg=False):
        self.conn = conn
        self.is_pg = is_pg

    def __enter__(self):
        self.conn.__enter__()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.conn.__exit__(exc_type, exc_val, exc_tb)

    def execute(self, sql, params=()):
        if self.is_pg:
            from psycopg2.extras import DictCursor

            sql = sql.replace("?", "%s")
            if "AUTOINCREMENT" in sql:
                sql = sql.replace("INTEGER PRIMARY KEY AUTOINCREMENT", "SERIAL PRIMARY KEY")
            
            cursor = self.conn.cursor(cursor_factory=DictCursor)
        else:
            cursor = self.conn.cursor()
            
        cursor.execute(sql, params)
        return cursor
        
    def commit(self):
        self.conn.commit()
        
    @property
    def row_factory(self):
        if self.is_pg:
            return None
        return self.conn.row_factory
        
    @row_factory.setter
    def row_factory(self, factory):
        if not self.is_pg:
            self.conn.row_factory = factory

def connect_db():
    db_url = os.environ.get("DATABASE_URL")
    if db_url and db_url.startswith("postgres"):
        try:
            import psycopg2
            from psycopg2.extras import DictCursor
        except ImportError as exc:
            raise RuntimeError(
                "Postgres DATABASE_URL requires psycopg2-binary to be installed"
            ) from exc
        conn = psycopg2.connect(db_url)
        return DBWrapper(conn, is_pg=True)
    else:
        db_path = Path(config.trade_db_path)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(db_path)
        conn.execute("PRAGMA journal_mode=MEMORY")
        return DBWrapper(conn, is_pg=False)

def init_db() -> None:
    with connect_db() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT NOT NULL,
                symbol TEXT NOT NULL,
                name TEXT NOT NULL,
                action TEXT NOT NULL,
                qty INTEGER NOT NULL,
                price INTEGER NOT NULL,
                reason TEXT,
                ok INTEGER NOT NULL,
                env TEXT,
                dry_run INTEGER
            )
            """
        )
        _ensure_column(conn, "trades", "broker_order_id", "TEXT")
        _ensure_column(conn, "trades", "order_status", "TEXT")
        _ensure_column(conn, "trades", "filled_qty", "INTEGER DEFAULT 0")
        _ensure_column(conn, "trades", "filled_price", "INTEGER DEFAULT 0")
        _ensure_column(conn, "trades", "pre_order_qty", "INTEGER DEFAULT 0")
        _ensure_column(conn, "trades", "response_msg", "TEXT")
        _ensure_column(conn, "trades", "broker_result", "TEXT")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS decision_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT NOT NULL,
                symbol TEXT NOT NULL,
                name TEXT NOT NULL,
                action TEXT NOT NULL,
                qty INTEGER NOT NULL,
                price INTEGER NOT NULL,
                reason TEXT,
                indicators TEXT,
                approved INTEGER NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS scanned_candidates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                scanned_at TEXT NOT NULL,
                symbol TEXT NOT NULL,
                name TEXT NOT NULL,
                score INTEGER NOT NULL,
                reasons TEXT,
                price INTEGER,
                env TEXT NOT NULL,
                rsi REAL,
                rsi2 REAL,
                macd_hist REAL,
                sma20 REAL,
                sma60 REAL
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_scanned_candidates_scanned_at ON scanned_candidates(scanned_at)")


def _ensure_column(conn: DBWrapper, table: str, column: str, column_type: str) -> None:
    if conn.is_pg:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column} {column_type}")
        return
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    existing = {row[1] for row in rows}
    if column not in existing:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {column_type}")


def _extract_broker_order_id(broker_result: dict | None) -> str:
    if not isinstance(broker_result, dict):
        return ""
    output = broker_result.get("output")
    if isinstance(output, dict):
        for key in ("ODNO", "odno", "order_no", "ord_no"):
            value = output.get(key)
            if value:
                return str(value)
    for key in ("ODNO", "odno", "order_no", "ord_no"):
        value = broker_result.get(key)
        if value:
            return str(value)
    return ""


def save_trade(
    symbol: str,
    name: str,
    action: str,
    qty: int,
    price: int,
    reason: str,
    ok: bool,
    order_submission_enabled: bool,
    *,
    broker_result: dict | None = None,
    order_status: str | None = None,
    response_msg: str | None = None,
    broker_order_id: str | None = None,
    filled_qty: int | None = None,
    filled_price: int | None = None,
    pre_order_qty: int | None = None,
) -> None:
    ts = datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S")
    broker_order_id = broker_order_id if broker_order_id is not None else _extract_broker_order_id(broker_result)
    order_status = order_status or ("submitted" if ok and order_submission_enabled else "simulated" if ok else "failed")
    filled_qty = qty if filled_qty is None and order_status in {"filled", "simulated"} else int(filled_qty or 0)
    filled_price = price if filled_price is None and filled_qty > 0 else int(filled_price or 0)
    if response_msg is None and isinstance(broker_result, dict):
        response_msg = str(broker_result.get("msg1", ""))
    response_msg = response_msg or ""
    pre_order_qty = int(pre_order_qty or 0)
    broker_result_json = json.dumps(broker_result or {}, ensure_ascii=False)
    try:
        init_db()
        with connect_db() as conn:
            conn.execute(
                """
                INSERT INTO trades (
                    ts, symbol, name, action, qty, price, reason, ok, env, dry_run,
                    broker_order_id, order_status, filled_qty, filled_price, pre_order_qty, response_msg, broker_result
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    ts,
                    symbol,
                    name,
                    action,
                    qty,
                    price,
                    reason,
                    int(ok),
                    config.trading_env,
                    int(not order_submission_enabled),
                    broker_order_id,
                    order_status,
                    filled_qty,
                    filled_price,
                    pre_order_qty,
                    response_msg,
                    broker_result_json,
                ),
            )
            
            # Export to JSON for cloud sync
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT ts, symbol, name, action, qty, price, reason, ok, env, dry_run,
                       broker_order_id, order_status, filled_qty, filled_price, pre_order_qty, response_msg, broker_result
                FROM trades ORDER BY ts ASC
                """
            ).fetchall()
            trades = [dict(row) for row in rows]
            
        # Use data/trades.json for GitHub Actions
        data_json_path = Path("data/trades.json")
        data_json_path.parent.mkdir(parents=True, exist_ok=True)
        with open(data_json_path, "w", encoding="utf-8") as f:
            json.dump(trades, f, ensure_ascii=False, indent=2)
            
    except Exception as e:
        logger.warning(f"Failed to save trade history: {e}")


def update_trade_order_status(
    broker_order_id: str,
    *,
    order_status: str,
    filled_qty: int = 0,
    filled_price: int = 0,
    response_msg: str = "",
    broker_result: dict | None = None,
) -> int:
    if not broker_order_id:
        return 0
    init_db()
    broker_result_json = json.dumps(broker_result or {}, ensure_ascii=False)
    with connect_db() as conn:
        cursor = conn.execute(
            """
            UPDATE trades
            SET order_status = ?,
                filled_qty = ?,
                filled_price = ?,
                response_msg = ?,
                broker_result = ?
            WHERE broker_order_id = ?
            """,
            (
                order_status,
                int(filled_qty or 0),
                int(filled_price or 0),
                response_msg,
                broker_result_json,
                broker_order_id,
            ),
        )
        return int(cursor.rowcount)

def save_decision_log(symbol: str, name: str, action: str, qty: int, price: int, reason: str, indicators: dict, approved: bool) -> None:
    ts = datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S")
    try:
        with connect_db() as conn:
            conn.execute(
                """
                INSERT INTO decision_logs (ts, symbol, name, action, qty, price, reason, indicators, approved)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (ts, symbol, name, action, qty, price, reason, json.dumps(indicators, ensure_ascii=False), int(approved))
            )
    except Exception as e:
        logger.warning(f"Failed to save decision log: {e}")


def save_scanned_candidate(
    symbol: str,
    name: str,
    score: int,
    reasons: list | str,
    price: int,
    env: str,
    indicators: dict | None = None
) -> None:
    ts = datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S")
    reasons_str = ",".join(reasons) if isinstance(reasons, list) else str(reasons)
    indicators = indicators or {}
    
    rsi = indicators.get("rsi")
    rsi2 = indicators.get("rsi2")
    macd_hist = indicators.get("macd_hist")
    sma20 = indicators.get("sma20")
    sma60 = indicators.get("sma60")
    
    try:
        init_db()
        with connect_db() as conn:
            conn.execute(
                """
                INSERT INTO scanned_candidates (
                    scanned_at, symbol, name, score, reasons, price, env,
                    rsi, rsi2, macd_hist, sma20, sma60
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    ts, symbol, name, score, reasons_str, price, env,
                    rsi, rsi2, macd_hist, sma20, sma60
                )
            )
    except Exception as e:
        logger.warning(f"Failed to save scanned candidate: {e}")


def get_scanned_candidates_history(limit: int = 100, days: int = 30) -> list[dict]:
    init_db()
    since_date = (datetime.now(KST) - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
    try:
        with connect_db() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT * FROM scanned_candidates
                WHERE scanned_at >= ?
                ORDER BY scanned_at DESC
                LIMIT ?
                """,
                (since_date, limit)
            ).fetchall()
            return [dict(row) for row in rows]
    except Exception as e:
        logger.warning(f"Failed to fetch scanned candidates history: {e}")
        return []


def delete_scanned_candidate(candidate_id: int) -> int:
    init_db()
    try:
        with connect_db() as conn:
            cursor = conn.execute(
                "DELETE FROM scanned_candidates WHERE id = ?",
                (candidate_id,)
            )
            return int(cursor.rowcount)
    except Exception as e:
        logger.warning(f"Failed to delete scanned candidate: {e}")
        return 0


TOKEN_USAGE_FILE = Path(".runtime/token_usage.json")

def _load_token_usage() -> dict:
    if not TOKEN_USAGE_FILE.exists():
        return {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "api_calls": 0}
    try:
        data = json.loads(TOKEN_USAGE_FILE.read_text(encoding="utf-8"))
        today = datetime.now(KST).strftime("%Y-%m-%d")
        if today in data:
            return data[today]
    except Exception:
        pass
    return {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "api_calls": 0}


def update_token_usage(prompt: int, completion: int, total: int | None = None) -> None:
    prompt = int(prompt or 0)
    completion = int(completion or 0)
    total = int(total or (prompt + completion))
    
    TOKEN_USAGE_FILE.parent.mkdir(parents=True, exist_ok=True)
    
    data = {}
    if TOKEN_USAGE_FILE.exists():
        try:
            data = json.loads(TOKEN_USAGE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
            
    today = datetime.now(KST).strftime("%Y-%m-%d")
    today_data = data.setdefault(today, {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "api_calls": 0})
    
    today_data["prompt_tokens"] += prompt
    today_data["completion_tokens"] += completion
    today_data["total_tokens"] += total
    today_data["api_calls"] += 1
    
    try:
        sorted_keys = sorted(data.keys())
        if len(sorted_keys) > 30:
            for key in sorted_keys[:-30]:
                data.pop(key, None)
        TOKEN_USAGE_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        logger.warning(f"Failed to save token usage: {e}")


AI_STRATEGIES_FILE = Path(".runtime/ai_strategies.json")

def load_ai_strategies() -> list[dict]:
    default_strategies = [
        {
            "id": "gpt_5_mini_default",
            "name": "🤖 GPT-5-mini 기본 추론 랭커",
            "provider": "openai",
            "model": "gpt-5-mini",
            "weight": 0.4,
            "description": "기술적 룰베이스 점수와 GPT-5-mini의 단기 반등 추론 점수를 6:4 비율로 결합하는 표준 AI 랭커입니다.",
            "selected": True
        },
        {
            "id": "rule_only_default",
            "name": "⚙️ 기본 기술 룰베이스 랭커",
            "provider": "none",
            "model": "none",
            "weight": 0.0,
            "description": "OpenAI API 호출 없이 정량적 기술 지표 규칙(RSI, MACD, SMA)만을 조합하여 0~5점 척도로 계산합니다.",
            "selected": False
        },
        {
            "id": "ranker_lgbm_v3",
            "name": "📊 LightGBM 순위 예측 랭커 (v3)",
            "provider": "none",
            "model": "ranker_lgbm_v3",
            "weight": 0.5,
            "description": "LightGBM 모델을 사용하여 종목의 상승 확률 및 순위를 고속으로 정밀 예측하는 단기 스코어링 엔진입니다.",
            "selected": False
        },
        {
            "id": "allocator_v2",
            "name": "⚖️ 리스크 예산 배분기 (v2)",
            "provider": "none",
            "model": "allocator_v2",
            "weight": 0.3,
            "description": "변동성 역수와 점수 분포 틸팅(MPT) 기법을 개량하여 포트폴리오의 리스크 부담을 지능적으로 예산화하여 배분합니다.",
            "selected": False
        },
        {
            "id": "ppo_policy_v1",
            "name": "🧠 PPO 강화학습 최적 정책 (v1)",
            "provider": "none",
            "model": "ppo_policy_v1",
            "weight": 0.6,
            "description": "Proximal Policy Optimization (PPO) 알고리즘으로 훈련된 강화학습 에이전트가 변동성 및 추세를 바탕으로 최적의 거래 액션을 도출합니다.",
            "selected": False
        }
    ]
    
    if not AI_STRATEGIES_FILE.exists():
        save_ai_strategies(default_strategies)
        return default_strategies
        
    try:
        data = json.loads(AI_STRATEGIES_FILE.read_text(encoding="utf-8"))
        if isinstance(data, list):
            existing_ids = {s.get("id") for s in data}
            needs_update = False
            for ds in default_strategies:
                if ds["id"] not in existing_ids:
                    data.append(ds)
                    needs_update = True
            
            if needs_update:
                save_ai_strategies(data)
                
            if not any(s.get("selected") for s in data):
                data[0]["selected"] = True
                save_ai_strategies(data)
            return data
    except Exception as e:
        logger.warning(f"Failed to load AI strategies: {e}")
        
    return default_strategies


def save_ai_strategies(strategies: list[dict]) -> None:
    try:
        AI_STRATEGIES_FILE.parent.mkdir(parents=True, exist_ok=True)
        AI_STRATEGIES_FILE.write_text(json.dumps(strategies, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        logger.warning(f"Failed to save AI strategies: {e}")


WATCHLIST_FILE = Path(".runtime/watchlist.json")

def load_watchlist_data() -> dict:
    default_data = {
        "symbols": ["005930", "000660", "035420", "035720", "005380", "207940", "068270", "051910"],
        "ai_auto_add": False
    }
    if not WATCHLIST_FILE.exists():
        save_watchlist_data(default_data)
        return default_data
    try:
        data = json.loads(WATCHLIST_FILE.read_text(encoding="utf-8"))
        if isinstance(data, dict) and "symbols" in data:
            if "ai_auto_add" not in data:
                data["ai_auto_add"] = False
            return data
    except Exception as e:
        logger.warning(f"Failed to load watchlist: {e}")
    return default_data

def save_watchlist_data(data: dict) -> None:
    try:
        WATCHLIST_FILE.parent.mkdir(parents=True, exist_ok=True)
        WATCHLIST_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        logger.warning(f"Failed to save watchlist: {e}")


