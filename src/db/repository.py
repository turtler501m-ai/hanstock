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
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS watchlist (
                symbol TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS watchlist_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS ai_strategies (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                provider TEXT NOT NULL,
                model TEXT NOT NULL,
                weight REAL NOT NULL,
                description TEXT,
                selected INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS token_usage (
                date TEXT PRIMARY KEY,
                prompt_tokens INTEGER NOT NULL,
                completion_tokens INTEGER NOT NULL,
                total_tokens INTEGER NOT NULL,
                api_calls INTEGER NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS auto_approval (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS scheduler_results (
                recorded_at TEXT PRIMARY KEY,
                mode TEXT NOT NULL,
                result TEXT NOT NULL
            )
            """
        )


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
    today = datetime.now(KST).strftime("%Y-%m-%d")
    try:
        init_db()
        with connect_db() as conn:
            conn.row_factory = sqlite3.Row
            c = conn.execute("SELECT * FROM token_usage WHERE date = ?", (today,))
            row = c.fetchone()
            if row is not None:
                return {
                    "prompt_tokens": int(row["prompt_tokens"]),
                    "completion_tokens": int(row["completion_tokens"]),
                    "total_tokens": int(row["total_tokens"]),
                    "api_calls": int(row["api_calls"])
                }
    except Exception as e:
        logger.warning(f"Failed to load token usage from DB: {e}")
        
    # Fallback to JSON
    if TOKEN_USAGE_FILE.exists():
        try:
            data = json.loads(TOKEN_USAGE_FILE.read_text(encoding="utf-8"))
            if today in data:
                return data[today]
        except Exception:
            pass
    return {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "api_calls": 0}


def update_token_usage(prompt: int, completion: int, total: int | None = None) -> None:
    prompt = int(prompt or 0)
    completion = int(completion or 0)
    total = int(total or (prompt + completion))
    today = datetime.now(KST).strftime("%Y-%m-%d")
    
    # Update in DB
    try:
        init_db()
        with connect_db() as conn:
            c = conn.execute("SELECT * FROM token_usage WHERE date = ?", (today,))
            row = c.fetchone()
            if row is not None:
                conn.execute(
                    """
                    UPDATE token_usage
                    SET prompt_tokens = prompt_tokens + ?,
                        completion_tokens = completion_tokens + ?,
                        total_tokens = total_tokens + ?,
                        api_calls = api_calls + 1
                    WHERE date = ?
                    """,
                    (prompt, completion, total, today)
                )
            else:
                conn.execute(
                    """
                    INSERT INTO token_usage (date, prompt_tokens, completion_tokens, total_tokens, api_calls)
                    VALUES (?, ?, ?, ?, 1)
                    """,
                    (today, prompt, completion, total)
                )
            conn.commit()
    except Exception as e:
        logger.warning(f"Failed to update token usage in DB: {e}")
        
    # Fallback/Sync to JSON
    try:
        TOKEN_USAGE_FILE.parent.mkdir(parents=True, exist_ok=True)
        data = {}
        if TOKEN_USAGE_FILE.exists():
            try:
                data = json.loads(TOKEN_USAGE_FILE.read_text(encoding="utf-8"))
            except Exception:
                pass
        today_data = data.setdefault(today, {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "api_calls": 0})
        today_data["prompt_tokens"] += prompt
        today_data["completion_tokens"] += completion
        today_data["total_tokens"] += total
        today_data["api_calls"] += 1
        
        sorted_keys = sorted(data.keys())
        if len(sorted_keys) > 30:
            for key in sorted_keys[:-30]:
                data.pop(key, None)
        TOKEN_USAGE_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        logger.warning(f"Failed to save token usage to JSON: {e}")


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
    
    try:
        init_db()
        with connect_db() as conn:
            conn.row_factory = sqlite3.Row
            c = conn.execute("SELECT * FROM ai_strategies ORDER BY id ASC")
            rows = c.fetchall()
            if len(rows) > 0:
                strategies = []
                for row in rows:
                    strategies.append({
                        "id": row["id"],
                        "name": row["name"],
                        "provider": row["provider"],
                        "model": row["model"],
                        "weight": float(row["weight"]),
                        "description": row["description"],
                        "selected": row["selected"] == 1
                    })
                return strategies
    except Exception as e:
        logger.warning(f"Failed to load AI strategies from DB: {e}")
        
    # Fallback/Migration: Load from JSON if exists, else defaults
    strategies = default_strategies
    if AI_STRATEGIES_FILE.exists():
        try:
            strategies = json.loads(AI_STRATEGIES_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
            
    # Migrate JSON/defaults into DB
    try:
        save_ai_strategies(strategies)
    except Exception:
        pass
    return strategies


def save_ai_strategies(strategies: list[dict]) -> None:
    # Save to JSON as backup
    try:
        AI_STRATEGIES_FILE.parent.mkdir(parents=True, exist_ok=True)
        AI_STRATEGIES_FILE.write_text(json.dumps(strategies, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        logger.warning(f"Failed to save AI strategies to JSON: {e}")
        
    # Save to DB
    try:
        init_db()
        with connect_db() as conn:
            # Clear and rebuild
            conn.execute("DELETE FROM ai_strategies")
            for s in strategies:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO ai_strategies (id, name, provider, model, weight, description, selected)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        s["id"],
                        s["name"],
                        s["provider"],
                        s["model"],
                        float(s["weight"]),
                        s.get("description", ""),
                        1 if s.get("selected", False) else 0
                    )
                )
            conn.commit()
    except Exception as e:
        logger.warning(f"Failed to save AI strategies to DB: {e}")


def save_scheduler_result(mode: str, recorded_at: str, result: dict) -> None:
    try:
        init_db()
        with connect_db() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO scheduler_results (recorded_at, mode, result) VALUES (?, ?, ?)",
                (recorded_at, mode, json.dumps(result, ensure_ascii=False))
            )
            conn.commit()
    except Exception as e:
        logger.warning(f"Failed to save scheduler result to DB: {e}")


def load_latest_scheduler_result() -> dict | None:
    try:
        init_db()
        with connect_db() as conn:
            conn.row_factory = sqlite3.Row
            c = conn.execute(
                "SELECT * FROM scheduler_results ORDER BY recorded_at DESC LIMIT 1"
            )
            row = c.fetchone()
            if row is not None:
                return {
                    "mode": row["mode"],
                    "recorded_at": row["recorded_at"],
                    "result": json.loads(row["result"])
                }
    except Exception as e:
        logger.warning(f"Failed to load scheduler result from DB: {e}")
    return None


def load_auto_approval_state() -> bool:
    try:
        init_db()
        with connect_db() as conn:
            c = conn.execute("SELECT value FROM auto_approval WHERE key = 'enabled'")
            row = c.fetchone()
            if row is not None:
                return row[0] == "1"
    except Exception as e:
        logger.warning(f"Failed to load auto approval state: {e}")
    return False


def save_auto_approval_state(enabled: bool) -> None:
    try:
        init_db()
        with connect_db() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO auto_approval (key, value) VALUES ('enabled', ?)",
                ("1" if enabled else "0",)
            )
            conn.commit()
    except Exception as e:
        logger.warning(f"Failed to save auto approval state: {e}")


WATCHLIST_FILE = Path(".runtime/watchlist.json")

STOCK_NAMES: dict[str, str] = {
    "005930": "삼성전자", "000660": "SK하이닉스", "035420": "NAVER", "035720": "카카오",
    "005380": "현대차", "207940": "삼성바이오로직스", "068270": "셀트리온", "051910": "LG화학",
    "018260": "삼성SDS", "009150": "삼성전기", "066570": "LG전자", "000270": "기아",
    "012330": "현대모비스", "003490": "대한항공", "011200": "HMM", "000100": "유한양행",
    "196170": "알테오젠", "145020": "휴젤", "105560": "KB금융", "055550": "신한지주",
    "086790": "하나금융지주", "316140": "우리금융지주", "032830": "삼성생명",
    "024110": "기업은행", "138040": "메리츠금융지주", "006400": "삼성SDI",
    "096770": "SK이노베이션", "011170": "롯데케미칼", "010950": "S-Oil",
    "003670": "포스코퓨처엠", "009830": "한화솔루션", "011780": "금호석유",
    "377300": "카카오페이", "005490": "POSCO홀딩스", "010130": "고려아연",
    "004020": "현대제철", "011790": "SKC", "017670": "SK텔레콤", "030200": "KT",
    "032640": "LG유플러스", "000720": "현대건설", "034020": "두산에너빌리티",
    "042660": "한화오션", "267250": "HD현대중공업", "082740": "HSD엔진",
    "012450": "한화에어로스페이스", "064350": "현대로템", "272210": "한화시스템",
    "047810": "한국항공우주", "097950": "CJ제일제당", "033780": "KT&G",
    "023530": "롯데쇼핑", "021240": "코웨이", "003550": "LG", "034730": "SK",
    "028260": "삼성물산", "000150": "두산", "047050": "포스코인터내셔널",
    "247540": "에코프로비엠", "086520": "에코프로", "259960": "크래프톤",
    "352820": "하이브", "251270": "넷마블", "036570": "엔씨소프트",
    "293490": "카카오게임즈", "323410": "카카오뱅크", "091990": "셀트리온헬스케어",
}

KOSPI_UNIVERSE = [
    # 시가총액 상위 (IT/반도체)
    "005930", "000660", "035420", "035720", "018260", "009150", "066570",
    # 자동차/운송
    "005380", "000270", "012330", "003490", "011200",
    # 바이오/제약
    "207940", "068270", "000100", "091990", "196170", "145020",
    # 금융
    "105560", "055550", "086790", "316140", "032830", "024110", "138040",
    # 화학/에너지
    "051910", "006400", "096770", "011170", "010950", "003670", "009830",
    "011780", "377300",
    # 철강/소재
    "005490", "010130", "004020", "011790",
    # 통신
    "017670", "030200", "032640",
    # 건설/중공업
    "000720", "034020", "042660", "267250", "082740",
    # 방산/항공
    "012450", "064350", "272210", "047810",
    # 유통/소비재
    "097950", "033780", "023530", "021240",
    # 지주/기타
    "003550", "034730", "028260", "000150", "047050",
    # KOSDAQ 주요종목
    "247540", "086520", "259960", "352820", "251270", "036570", "293490",
    "323410", "377300",
]
KOSPI_UNIVERSE = list(dict.fromkeys(KOSPI_UNIVERSE))


def load_watchlist_data() -> dict:
    try:
        init_db()
        with connect_db() as conn:
            c = conn.execute("SELECT symbol FROM watchlist ORDER BY symbol ASC")
            symbols = [row[0] for row in c.fetchall()]
            
            # 종목 개수가 현저히 적으면 KOSPI_UNIVERSE 자동 마이그레이션 및 DB 저장
            if len(symbols) < 20:
                merged = list(dict.fromkeys(symbols + KOSPI_UNIVERSE))
                ts = datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S")
                for s in merged:
                    if s not in symbols:
                        name = STOCK_NAMES.get(s, "우량 종목")
                        conn.execute(
                            "INSERT OR IGNORE INTO watchlist (symbol, name, created_at) VALUES (?, ?, ?)",
                            (s, name, ts)
                        )
                conn.commit()
                symbols = merged
            
            c_set = conn.execute("SELECT value FROM watchlist_settings WHERE key = 'ai_auto_add'")
            row_set = c_set.fetchone()
            if row_set is None:
                conn.execute("INSERT OR IGNORE INTO watchlist_settings (key, value) VALUES ('ai_auto_add', '0')")
                conn.commit()
                ai_auto_add = False
            else:
                ai_auto_add = (row_set[0] == '1')
                
            c_thresh = conn.execute("SELECT value FROM watchlist_settings WHERE key = 'ai_auto_add_threshold'")
            row_thresh = c_thresh.fetchone()
            if row_thresh is None:
                conn.execute("INSERT OR IGNORE INTO watchlist_settings (key, value) VALUES ('ai_auto_add_threshold', '3.0')")
                conn.commit()
                ai_auto_add_threshold = 3.0
            else:
                try:
                    ai_auto_add_threshold = float(row_thresh[0])
                except ValueError:
                    ai_auto_add_threshold = 3.0
                
            return {
                "symbols": symbols,
                "ai_auto_add": ai_auto_add,
                "ai_auto_add_threshold": ai_auto_add_threshold
            }
    except Exception as e:
        logger.warning(f"Failed to load watchlist from DB: {e}")
        return {
            "symbols": KOSPI_UNIVERSE,
            "ai_auto_add": False,
            "ai_auto_add_threshold": 3.0
        }


def save_watchlist_data(data: dict) -> None:
    try:
        init_db()
        with connect_db() as conn:
            if "ai_auto_add" in data:
                ai_auto_add_val = "1" if data["ai_auto_add"] else "0"
                conn.execute(
                    "INSERT OR REPLACE INTO watchlist_settings (key, value) VALUES ('ai_auto_add', ?)",
                    (ai_auto_add_val,)
                )
            
            if "ai_auto_add_threshold" in data:
                conn.execute(
                    "INSERT OR REPLACE INTO watchlist_settings (key, value) VALUES ('ai_auto_add_threshold', ?)",
                    (str(float(data["ai_auto_add_threshold"])),)
                )
            
            if "symbols" in data:
                conn.execute("DELETE FROM watchlist")
                ts = datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S")
                for s in data["symbols"]:
                    name = STOCK_NAMES.get(s, "우량 종목")
                    conn.execute(
                        "INSERT OR IGNORE INTO watchlist (symbol, name, created_at) VALUES (?, ?, ?)",
                        (s, name, ts)
                    )
            conn.commit()
    except Exception as e:
        logger.warning(f"Failed to save watchlist to DB: {e}")


