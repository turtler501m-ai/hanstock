import sqlite3
import os
import json
import hashlib
from pathlib import Path
from datetime import datetime, timedelta, timezone
from src.config import config
from src.utils.logger import logger

KST = timezone(timedelta(hours=9))

class DBWrapper:
    def __init__(self, conn, is_pg=False, close_on_exit=False):
        self.conn = conn
        self.is_pg = is_pg
        self.close_on_exit = close_on_exit

    def __enter__(self):
        self.conn.__enter__()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        try:
            return self.conn.__exit__(exc_type, exc_val, exc_tb)
        finally:
            if self.close_on_exit:
                self.conn.close()

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
        return DBWrapper(conn, is_pg=True, close_on_exit=True)
    else:
        db_path = Path(config.trade_db_path)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(db_path)
        conn.execute("PRAGMA journal_mode=MEMORY")
        return DBWrapper(conn, is_pg=False, close_on_exit=True)

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
        _ensure_column(conn, "trades", "strategy_id", "TEXT")
        _ensure_column(conn, "trades", "strategy_version", "INTEGER")
        _ensure_column(conn, "trades", "profile_hash", "TEXT")
        _ensure_column(conn, "trades", "source_approval_id", "INTEGER")
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
        _ensure_column(conn, "ai_strategies", "status", "TEXT DEFAULT 'draft'")
        _ensure_column(conn, "ai_strategies", "profile_json", "TEXT")
        _ensure_column(conn, "ai_strategies", "strategy_version", "INTEGER DEFAULT 1")
        _ensure_column(conn, "ai_strategies", "profile_hash", "TEXT")
        _ensure_column(conn, "ai_strategies", "last_verified_at", "TEXT")
        _ensure_column(conn, "ai_strategies", "last_backtested_at", "TEXT")
        _ensure_column(conn, "ai_strategies", "last_paper_started_at", "TEXT")
        _ensure_column(conn, "ai_strategies", "last_paper_completed_at", "TEXT")
        _ensure_column(conn, "ai_strategies", "last_used_at", "TEXT")
        _ensure_column(conn, "ai_strategies", "last_validation_result", "TEXT")
        _ensure_column(conn, "scanned_candidates", "strategy_id", "TEXT")
        _ensure_column(conn, "scanned_candidates", "strategy_version", "INTEGER")
        _ensure_column(conn, "scanned_candidates", "profile_hash", "TEXT")
        _ensure_column(conn, "scanned_candidates", "ranker_model", "TEXT")
        _ensure_column(conn, "scanned_candidates", "optimizer", "TEXT")
        _ensure_column(conn, "scanned_candidates", "rule_score", "REAL")
        _ensure_column(conn, "scanned_candidates", "ml_score", "REAL")
        _ensure_column(conn, "scanned_candidates", "final_score", "REAL")
        _ensure_column(conn, "scanned_candidates", "ai_model_status", "TEXT")
        _ensure_column(conn, "scanned_candidates", "ai_fallback_reason", "TEXT")
        _ensure_column(conn, "scanned_candidates", "top_features_json", "TEXT")
        _ensure_column(conn, "scanned_candidates", "forward_return_1d", "REAL")
        _ensure_column(conn, "scanned_candidates", "forward_return_5d", "REAL")
        _ensure_column(conn, "scanned_candidates", "forward_return_20d", "REAL")
        _ensure_column(conn, "scanned_candidates", "return_updated_at", "TEXT")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS ai_strategy_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT NOT NULL,
                strategy_id TEXT NOT NULL,
                strategy_version INTEGER,
                event_type TEXT NOT NULL,
                payload TEXT
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
        _ensure_column(conn, "approvals", "strategy_id", "TEXT")
        _ensure_column(conn, "approvals", "strategy_version", "INTEGER")
        _ensure_column(conn, "approvals", "profile_hash", "TEXT")
        _ensure_column(conn, "approvals", "source_candidate_id", "INTEGER")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS scheduler_results (
                recorded_at TEXT PRIMARY KEY,
                mode TEXT NOT NULL,
                result TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS daily_charts (
                symbol TEXT,
                date TEXT,
                open REAL,
                high REAL,
                low REAL,
                close REAL,
                volume REAL,
                PRIMARY KEY (symbol, date)
            )
            """
        )
        
        # 일회성 관심종목 클린업 마이그레이션 (더 많은 AI 자동 추가 자리를 확보하기 위함)
        try:
            c_mig = conn.execute("SELECT value FROM watchlist_settings WHERE key = 'migration_watchlist_cleaned_v3'")
            row_mig = c_mig.fetchone()
            if row_mig is None or row_mig[0] != '1':
                c = conn.execute("SELECT COUNT(*) FROM watchlist")
                count = c.fetchone()[0]
                if count > 20:
                    conn.execute("DELETE FROM watchlist")
                    ts = datetime.now(timezone(timedelta(hours=9))).strftime("%Y-%m-%d %H:%M:%S")
                    default_symbols = ["005930", "000660", "035420", "005380", "035720"]
                    for s in default_symbols:
                        conn.execute(
                            "INSERT OR IGNORE INTO watchlist (symbol, name, created_at) VALUES (?, '우량 종목', ?)",
                            (s, ts)
                        )
                    logger.info("[MIGRATION] Watchlist cleaned up to 5 default symbols for AI slots.")
                conn.execute("INSERT OR REPLACE INTO watchlist_settings (key, value) VALUES ('migration_watchlist_cleaned_v3', '1')")
                conn.commit()
        except Exception as m_err:
            logger.warning(f"Failed to run watchlist migration clean up: {m_err}")


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
    strategy_id: str | None = None,
    strategy_version: int | None = None,
    profile_hash: str | None = None,
    source_approval_id: int | None = None,
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
                    broker_order_id, order_status, filled_qty, filled_price, pre_order_qty, response_msg, broker_result,
                    strategy_id, strategy_version, profile_hash, source_approval_id
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    strategy_id,
                    strategy_version,
                    profile_hash,
                    source_approval_id,
                ),
            )
            
            # Export to JSON for cloud sync
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT ts, symbol, name, action, qty, price, reason, ok, env, dry_run,
                       broker_order_id, order_status, filled_qty, filled_price, pre_order_qty, response_msg, broker_result,
                       strategy_id, strategy_version, profile_hash, source_approval_id
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
    indicators: dict | None = None,
    strategy: dict | None = None,
    ranker_model: str | None = None,
    optimizer: str | None = None,
    scoring: dict | None = None,
) -> int | None:
    ts = datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S")
    reasons_str = ",".join(reasons) if isinstance(reasons, list) else str(reasons)
    indicators = indicators or {}
    
    rsi = indicators.get("rsi")
    rsi2 = indicators.get("rsi2")
    macd_hist = indicators.get("macd_hist")
    sma20 = indicators.get("sma20")
    sma60 = indicators.get("sma60")
    strategy = strategy or {}
    scoring = scoring or {}
    top_features = scoring.get("top_features")
    top_features_json = (
        json.dumps(top_features, ensure_ascii=False)
        if isinstance(top_features, (list, dict))
        else None
    )
    
    try:
        init_db()
        with connect_db() as conn:
            cursor = conn.execute(
                """
                INSERT INTO scanned_candidates (
                    scanned_at, symbol, name, score, reasons, price, env,
                    rsi, rsi2, macd_hist, sma20, sma60,
                    strategy_id, strategy_version, profile_hash, ranker_model, optimizer,
                    rule_score, ml_score, final_score, ai_model_status,
                    ai_fallback_reason, top_features_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    ts, symbol, name, score, reasons_str, price, env,
                    rsi, rsi2, macd_hist, sma20, sma60,
                    strategy.get("id"),
                    strategy.get("strategy_version"),
                    strategy.get("profile_hash"),
                    ranker_model,
                    optimizer,
                    scoring.get("rule_score"),
                    scoring.get("ml_score"),
                    scoring.get("final_score"),
                    scoring.get("ai_model_status"),
                    scoring.get("ai_fallback_reason"),
                    top_features_json,
                )
            )
            return int(cursor.lastrowid)
    except Exception as e:
        logger.warning(f"Failed to save scanned candidate: {e}")
    return None


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


def _candidate_date(scanned_at: str) -> str:
    return str(scanned_at or "")[:10]


def _chart_close_on_or_after(conn: DBWrapper, symbol: str, date_text: str) -> tuple[str, float] | None:
    row = conn.execute(
        """
        SELECT date, close
        FROM daily_charts
        WHERE symbol = ?
          AND date >= ?
          AND close > 0
        ORDER BY date ASC
        LIMIT 1
        """,
        (symbol, date_text),
    ).fetchone()
    if not row:
        return None
    return str(row[0]), float(row[1])


def _target_date(date_text: str, days: int) -> str:
    return (datetime.fromisoformat(date_text) + timedelta(days=days)).strftime("%Y-%m-%d")


def refresh_scanned_candidate_forward_returns(
    *,
    days: tuple[int, ...] = (1, 5, 20),
    limit: int = 500,
) -> dict:
    init_db()
    supported_days = tuple(day for day in days if day in {1, 5, 20})
    if not supported_days:
        return {"ok": True, "checked_count": 0, "updated_count": 0, "days": []}

    null_checks = " OR ".join(f"forward_return_{day}d IS NULL" for day in supported_days)
    with connect_db() as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            f"""
            SELECT id, scanned_at, symbol, price
            FROM scanned_candidates
            WHERE ({null_checks})
            ORDER BY scanned_at ASC
            LIMIT ?
            """,
            (max(1, min(int(limit or 500), 5000)),),
        ).fetchall()

        updated_count = 0
        skipped_count = 0
        now = datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S")
        for row in rows:
            item = dict(row)
            scanned_date = _candidate_date(item.get("scanned_at", ""))
            symbol = str(item.get("symbol") or "")
            if not scanned_date or not symbol:
                skipped_count += 1
                continue

            base = _chart_close_on_or_after(conn, symbol, scanned_date)
            if base is None:
                skipped_count += 1
                continue
            _, base_close = base
            if base_close <= 0:
                skipped_count += 1
                continue

            values: dict[str, float] = {}
            for day in supported_days:
                target = _chart_close_on_or_after(conn, symbol, _target_date(scanned_date, day))
                if target is None:
                    continue
                _, target_close = target
                values[f"forward_return_{day}d"] = round(((target_close - base_close) / base_close) * 100, 4)

            if not values:
                skipped_count += 1
                continue

            assignments = ", ".join(f"{key} = ?" for key in values)
            params = [*values.values(), now, int(item["id"])]
            cursor = conn.execute(
                f"""
                UPDATE scanned_candidates
                SET {assignments},
                    return_updated_at = ?
                WHERE id = ?
                """,
                tuple(params),
            )
            updated_count += int(cursor.rowcount)

    return {
        "ok": True,
        "checked_count": len(rows),
        "updated_count": updated_count,
        "skipped_count": skipped_count,
        "days": list(supported_days),
    }


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

def _default_strategy_profile(strategy: dict) -> dict:
    provider = strategy.get("provider") or ("openai" if strategy.get("model") != "none" else "rule")
    model = strategy.get("model", "none")
    weight = max(0.0, min(1.0, float(strategy.get("weight", 0.0) or 0.0)))
    if provider == "none":
        provider = "rule" if model == "none" else str(model).split("_", 1)[0]
    return {
        "strategy_type": strategy.get("strategy_type", "rebound"),
        "risk_level": strategy.get("risk_level", "balanced"),
        "provider": provider,
        "model": model,
        "ai_weight": weight,
        "min_rule_score_for_ai": 1.5,
        "min_ai_confidence": 0.6,
        "allow_candidate_promotion": False,
        "focus": ["rsi2_oversold", "bollinger_lower_band", "volume_recovery"],
        "avoid": ["high_volatility_breakdown", "overheated_rsi", "weak_liquidity"],
        "market_regime_filter": ["neutral", "bull", "low_volatility"],
        "backtest": {
            "min_warmup_periods": 60,
            "commission_bps": 15,
            "slippage_bps": 5,
            "market_impact_bps": 5,
        },
        "risk": {
            "max_ai_weight": weight,
            "max_risk_per_trade_pct": 1.0,
            "max_daily_ai_orders": 3,
            "paper_trading_required_days": 20,
        },
    }


def _parse_strategy_profile(strategy: dict) -> dict:
    raw_profile = strategy.get("profile")
    if not raw_profile:
        raw_profile = strategy.get("profile_json")
    if isinstance(raw_profile, str) and raw_profile.strip():
        try:
            raw_profile = json.loads(raw_profile)
        except Exception:
            raw_profile = {}
    if not isinstance(raw_profile, dict):
        raw_profile = {}
    profile = _default_strategy_profile(strategy)
    profile.update(raw_profile)
    profile["model"] = str(profile.get("model") or strategy.get("model") or "none")
    profile["ai_weight"] = max(0.0, min(1.0, float(profile.get("ai_weight", strategy.get("weight", 0.0)) or 0.0)))
    return profile


def strategy_profile_hash(profile: dict) -> str:
    payload = json.dumps(profile or {}, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def normalize_ai_strategy(strategy: dict) -> dict:
    item = dict(strategy)
    item["provider"] = str(item.get("provider") or ("openai" if item.get("model") != "none" else "none"))
    item["model"] = str(item.get("model") or "none")
    item["weight"] = max(0.0, min(1.0, float(item.get("weight", 0.0) or 0.0)))
    item["selected"] = bool(item.get("selected", False))
    item["strategy_version"] = int(item.get("strategy_version") or 1)
    item["status"] = str(item.get("status") or ("approved" if item.get("selected") else "verified"))
    profile = _parse_strategy_profile(item)
    item["profile"] = profile
    item["profile_json"] = json.dumps(profile, ensure_ascii=False, sort_keys=True)
    item["profile_hash"] = strategy_profile_hash(profile)
    item["description"] = str(item.get("description") or "")
    for key in (
        "last_verified_at",
        "last_backtested_at",
        "last_paper_started_at",
        "last_paper_completed_at",
        "last_used_at",
        "last_validation_result",
    ):
        item[key] = item.get(key)
    return item


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
                    strategies.append(normalize_ai_strategy({
                        "id": row["id"],
                        "name": row["name"],
                        "provider": row["provider"],
                        "model": row["model"],
                        "weight": float(row["weight"]),
                        "description": row["description"],
                        "selected": row["selected"] == 1,
                        "status": row["status"] if "status" in row.keys() else None,
                        "profile_json": row["profile_json"] if "profile_json" in row.keys() else None,
                        "strategy_version": row["strategy_version"] if "strategy_version" in row.keys() else 1,
                        "profile_hash": row["profile_hash"] if "profile_hash" in row.keys() else None,
                        "last_verified_at": row["last_verified_at"] if "last_verified_at" in row.keys() else None,
                        "last_backtested_at": row["last_backtested_at"] if "last_backtested_at" in row.keys() else None,
                        "last_paper_started_at": row["last_paper_started_at"] if "last_paper_started_at" in row.keys() else None,
                        "last_paper_completed_at": row["last_paper_completed_at"] if "last_paper_completed_at" in row.keys() else None,
                        "last_used_at": row["last_used_at"] if "last_used_at" in row.keys() else None,
                        "last_validation_result": row["last_validation_result"] if "last_validation_result" in row.keys() else None,
                    }))
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
    return [normalize_ai_strategy(s) for s in strategies]


def save_ai_strategies(strategies: list[dict]) -> None:
    # Save to JSON as backup
    try:
        AI_STRATEGIES_FILE.parent.mkdir(parents=True, exist_ok=True)
        strategies = [normalize_ai_strategy(s) for s in strategies]
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
                    INSERT OR REPLACE INTO ai_strategies (
                        id, name, provider, model, weight, description, selected,
                        status, profile_json, strategy_version, profile_hash,
                        last_verified_at, last_backtested_at, last_paper_started_at,
                        last_paper_completed_at, last_used_at, last_validation_result
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        s["id"],
                        s["name"],
                        s["provider"],
                        s["model"],
                        float(s["weight"]),
                        s.get("description", ""),
                        1 if s.get("selected", False) else 0,
                        s.get("status", "draft"),
                        s.get("profile_json"),
                        int(s.get("strategy_version") or 1),
                        s.get("profile_hash"),
                        s.get("last_verified_at"),
                        s.get("last_backtested_at"),
                        s.get("last_paper_started_at"),
                        s.get("last_paper_completed_at"),
                        s.get("last_used_at"),
                        s.get("last_validation_result"),
                    )
                )
            conn.commit()
    except Exception as e:
        logger.warning(f"Failed to save AI strategies to DB: {e}")


def record_ai_strategy_event(
    strategy_id: str,
    event_type: str,
    payload: dict | None = None,
    strategy_version: int | None = None,
) -> None:
    ts = datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S")
    try:
        init_db()
        with connect_db() as conn:
            conn.execute(
                """
                INSERT INTO ai_strategy_events (ts, strategy_id, strategy_version, event_type, payload)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    ts,
                    strategy_id,
                    strategy_version,
                    event_type,
                    json.dumps(payload or {}, ensure_ascii=False),
                ),
            )
            conn.commit()
    except Exception as e:
        logger.warning(f"Failed to record AI strategy event: {e}")


def get_ai_strategy_events(strategy_id: str, limit: int = 100) -> list[dict]:
    try:
        init_db()
        with connect_db() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT * FROM ai_strategy_events
                WHERE strategy_id = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (strategy_id, limit),
            ).fetchall()
            return [dict(row) for row in rows]
    except Exception as e:
        logger.warning(f"Failed to fetch AI strategy events: {e}")
        return []


def get_ai_strategy_performance(strategy_id: str, days: int = 30) -> dict:
    init_db()
    since_date = (datetime.now(KST) - timedelta(days=max(1, int(days or 30)))).strftime("%Y-%m-%d %H:%M:%S")
    try:
        with connect_db() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT *
                FROM scanned_candidates
                WHERE strategy_id = ?
                  AND scanned_at >= ?
                ORDER BY scanned_at DESC
                """,
                (strategy_id, since_date),
            ).fetchall()
            candidates = [dict(row) for row in rows]
    except Exception as e:
        logger.warning(f"Failed to fetch AI strategy performance rows: {e}")
        candidates = []

    final_scores = [
        float(item.get("final_score"))
        for item in candidates
        if item.get("final_score") is not None
    ]
    rule_scores = [
        float(item.get("rule_score"))
        for item in candidates
        if item.get("rule_score") is not None
    ]
    ml_scores = [
        float(item.get("ml_score"))
        for item in candidates
        if item.get("ml_score") is not None
    ]
    return_1d = [
        float(item.get("forward_return_1d"))
        for item in candidates
        if item.get("forward_return_1d") is not None
    ]
    return_5d = [
        float(item.get("forward_return_5d"))
        for item in candidates
        if item.get("forward_return_5d") is not None
    ]
    return_20d = [
        float(item.get("forward_return_20d"))
        for item in candidates
        if item.get("forward_return_20d") is not None
    ]
    status_counts: dict[str, int] = {}
    optimizer_counts: dict[str, int] = {}
    for item in candidates:
        status = str(item.get("ai_model_status") or "unknown")
        optimizer = str(item.get("optimizer") or "unknown")
        status_counts[status] = status_counts.get(status, 0) + 1
        optimizer_counts[optimizer] = optimizer_counts.get(optimizer, 0) + 1

    def avg(values: list[float]) -> float | None:
        return round(sum(values) / len(values), 4) if values else None

    def win_rate(values: list[float]) -> float | None:
        return round((sum(1 for value in values if value > 0) / len(values)) * 100, 2) if values else None

    trade_summary = {
        "trade_count": 0,
        "order_count": 0,
        "approval_count": 0,
        "filled_count": 0,
        "fill_rate": None,
        "order_status_counts": {},
        "approval_status_counts": {},
    }
    try:
        with connect_db() as conn:
            conn.row_factory = sqlite3.Row
            approval_rows = conn.execute(
                """
                SELECT *
                FROM approvals
                WHERE strategy_id = ?
                  AND created_at >= ?
                ORDER BY created_at DESC
                """,
                (strategy_id, since_date),
            ).fetchall()
            approvals = [dict(row) for row in approval_rows]
            approval_status_counts: dict[str, int] = {}
            for approval in approvals:
                status = str(approval.get("status") or "unknown")
                approval_status_counts[status] = approval_status_counts.get(status, 0) + 1

            trade_rows = conn.execute(
                """
                SELECT *
                FROM trades
                WHERE strategy_id = ?
                  AND ts >= ?
                ORDER BY ts DESC
                """,
                (strategy_id, since_date),
            ).fetchall()
            trades = [dict(row) for row in trade_rows]
            status_counts_trade: dict[str, int] = {}
            for trade in trades:
                status = str(trade.get("order_status") or "unknown")
                status_counts_trade[status] = status_counts_trade.get(status, 0) + 1
            filled_count = sum(
                1
                for trade in trades
                if str(trade.get("order_status") or "") in {"filled", "simulated"}
                or int(trade.get("filled_qty") or 0) > 0
            )
            approval_count = len(approvals)
            order_count = approval_count if approval_count else len(trades)
            trade_summary = {
                "trade_count": len(trades),
                "approval_count": approval_count,
                "order_count": order_count,
                "filled_count": filled_count,
                "fill_rate": round((filled_count / order_count) * 100, 2) if order_count else None,
                "order_status_counts": status_counts_trade,
                "approval_status_counts": approval_status_counts,
                "recent_approvals": approvals[:20],
                "recent_trades": trades[:20],
            }
    except Exception as e:
        logger.warning(f"Failed to fetch AI strategy trade performance: {e}")

    return {
        "strategy_id": strategy_id,
        "days": days,
        "candidate_count": len(candidates),
        "avg_final_score": avg(final_scores),
        "avg_rule_score": avg(rule_scores),
        "avg_ml_score": avg(ml_scores),
        "avg_return_1d": avg(return_1d),
        "avg_return_5d": avg(return_5d),
        "avg_return_20d": avg(return_20d),
        "win_rate_1d": win_rate(return_1d),
        "win_rate_5d": win_rate(return_5d),
        "win_rate_20d": win_rate(return_20d),
        "return_sample_count_1d": len(return_1d),
        "return_sample_count_5d": len(return_5d),
        "return_sample_count_20d": len(return_20d),
        "trade_summary": trade_summary,
        "ai_model_status_counts": status_counts,
        "optimizer_counts": optimizer_counts,
        "recent_candidates": candidates[:20],
    }


def review_ai_strategy_performance(strategy_id: str, days: int = 30) -> dict:
    strategies = load_ai_strategies()
    target = next((item for item in strategies if item.get("id") == strategy_id), None)
    if target is None:
        return {"ok": False, "reason": "strategy_not_found", "strategy_id": strategy_id}

    performance = get_ai_strategy_performance(strategy_id, days=days)
    candidate_count = int(performance.get("candidate_count") or 0)
    status_counts = performance.get("ai_model_status_counts") or {}
    fallback_count = int(status_counts.get("fallback", 0)) + int(status_counts.get("disabled", 0))
    fallback_rate = (fallback_count / candidate_count) if candidate_count else 0.0
    avg_final_score = performance.get("avg_final_score")
    avg_return_5d = performance.get("avg_return_5d")
    fill_rate = (performance.get("trade_summary") or {}).get("fill_rate")
    warnings = []

    if candidate_count == 0:
        warnings.append("no candidates in review window")
    if candidate_count >= 5 and avg_final_score is not None and float(avg_final_score) < 2.5:
        warnings.append("low average final score")
    if candidate_count >= 5 and fallback_rate >= 0.5:
        warnings.append("high AI fallback rate")
    if candidate_count >= 5 and avg_return_5d is not None and float(avg_return_5d) < 0:
        warnings.append("negative 5-day candidate return")
    if fill_rate is not None and float(fill_rate) < 50:
        warnings.append("low order fill rate")

    previous_status = str(target.get("status") or "draft")
    new_status = previous_status
    if (
        candidate_count >= 10
        and avg_final_score is not None
        and float(avg_final_score) < 1.5
        and fallback_rate >= 0.8
    ):
        new_status = "retired"
    elif candidate_count >= 10 and avg_return_5d is not None and float(avg_return_5d) <= -5:
        new_status = "retired"
    elif warnings and previous_status in {"approved", "paper_passed", "backtested", "verified"}:
        new_status = "review_required"

    changed = new_status != previous_status
    if changed:
        for item in strategies:
            if item.get("id") == strategy_id:
                item["status"] = new_status
                if new_status == "retired":
                    item["selected"] = False
                target = item
                break
        save_ai_strategies(strategies)

    result = {
        "ok": True,
        "strategy_id": strategy_id,
        "days": days,
        "previous_status": previous_status,
        "new_status": new_status,
        "changed": changed,
        "warnings": warnings,
        "fallback_rate": round(fallback_rate, 4),
        "performance": performance,
    }
    record_ai_strategy_event(strategy_id, "performance_review", result, target.get("strategy_version"))
    return result


def save_scheduler_result(mode: str, recorded_at: str, result: dict) -> None:
    try:
        init_db()
        
        # Robust conversion of sets/unserializable types to list/str
        def convert_unserializable(obj):
            if isinstance(obj, dict):
                return {k: convert_unserializable(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [convert_unserializable(x) for x in obj]
            elif isinstance(obj, set):
                try:
                    return [convert_unserializable(x) for x in sorted(list(obj))]
                except Exception:
                    return [convert_unserializable(x) for x in list(obj)]
            return obj

        cleaned_result = convert_unserializable(result)
        
        with connect_db() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO scheduler_results (recorded_at, mode, result) VALUES (?, ?, ?)",
                (recorded_at, mode, json.dumps(cleaned_result, ensure_ascii=False, default=str))
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
                res_data = json.loads(row["result"])
                recorded_at_str = row["recorded_at"]
                time_part = recorded_at_str.replace("T", " ").split(" ")[1][:5]
                
                # Enrich with time and round
                if "results" in res_data:
                    for item in res_data["results"]:
                        item["time"] = time_part
                        item["round"] = 1
                if "auto_approved" in res_data:
                    for item in res_data["auto_approved"]:
                        item["time"] = time_part
                        item["round"] = 1
                if "auto_approval_errors" in res_data:
                    for item in res_data["auto_approval_errors"]:
                        item["time"] = time_part
                        item["round"] = 1

                return {
                    "mode": row["mode"],
                    "recorded_at": row["recorded_at"],
                    "result": res_data
                }
    except Exception as e:
        logger.warning(f"Failed to load scheduler result from DB: {e}")
    return None
 
 
def load_today_scheduler_results() -> dict | None:
    try:
        init_db()
        with connect_db() as conn:
            conn.row_factory = sqlite3.Row
            
            from datetime import datetime, timezone, timedelta
            KST = timezone(timedelta(hours=9))
            today_str = datetime.now(KST).strftime("%Y-%m-%d")
            
            c = conn.execute(
                "SELECT * FROM scheduler_results WHERE recorded_at >= ? ORDER BY recorded_at ASC",
                (f"{today_str} 00:00:00",)
            )
            rows = c.fetchall()
            if not rows:
                return None
                
            merged_results = []
            merged_approved = []
            merged_approval_errors = []
            merged_run_errors = []
            
            latest_recorded_at = rows[-1]["recorded_at"]
            latest_mode = rows[-1]["mode"]
            
            for idx, row in enumerate(rows):
                try:
                    res_data = json.loads(row["result"])
                except Exception:
                    continue
                
                round_num = idx + 1
                recorded_at_str = row["recorded_at"]
                time_part = recorded_at_str.replace("T", " ").split(" ")[1][:5]
                
                # plans / results
                for item in res_data.get("results", []):
                    item_copy = dict(item)
                    item_copy["time"] = time_part
                    item_copy["round"] = round_num
                    if "reason" in item_copy and item_copy["reason"]:
                        item_copy["reason"] = f"[{time_part}] {item_copy['reason']}"
                    else:
                        item_copy["reason"] = f"[{time_part}] 스케쥴 분석 결과"
                    merged_results.append(item_copy)
                    
                # approved / auto_approved
                for item in res_data.get("auto_approved", []):
                    item_copy = dict(item)
                    item_copy["time"] = time_part
                    item_copy["round"] = round_num
                    if "response_msg" in item_copy and item_copy["response_msg"]:
                        item_copy["response_msg"] = f"[{time_part}] {item_copy['response_msg']}"
                    else:
                        item_copy["response_msg"] = f"[{time_part}] 정상 처리"
                    merged_approved.append(item_copy)
                    
                # approval errors
                for item in res_data.get("auto_approval_errors", []):
                    item_copy = dict(item)
                    item_copy["time"] = time_part
                    item_copy["round"] = round_num
                    if "message" in item_copy and item_copy["message"]:
                        item_copy["message"] = f"[{time_part}] {item_copy['message']}"
                    else:
                        item_copy["message"] = f"[{time_part}] 오류 발생"
                    merged_approval_errors.append(item_copy)
                    
                # run errors
                errors = res_data.get("errors", []) or res_data.get("retry_errors", [])
                if isinstance(errors, list):
                    for err in errors:
                        merged_run_errors.append(f"[{time_part}] {err}")
                elif errors:
                    merged_run_errors.append(f"[{time_part}] {errors}")
                    
            return {
                "mode": latest_mode,
                "recorded_at": f"{today_str} (당일 전체 집계)",
                "result": {
                    "results": merged_results,
                    "auto_approved": merged_approved,
                    "auto_approval_errors": merged_approval_errors,
                    "errors": merged_run_errors,
                    "status": "success" if not merged_approval_errors and not merged_run_errors else "failed",
                    "ok": True
                }
            }
    except Exception as e:
        logger.warning(f"Failed to load today scheduler results from DB: {e}")
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
    "018260": "삼성에스디에스", "009150": "삼성전기", "066570": "LG전자", "034220": "LG디스플레이", 
    "000990": "DB하이텍", "042700": "한미반도체", "036930": "주성엔지니어링", "240810": "원익IPS", 
    "058470": "리노공업", "357780": "솔브레인", "039030": "이오테크닉스", "056190": "에스에프에이", 
    "067310": "하나마이크론", "005290": "동진쎄미켐", "012510": "더존비즈온", "053800": "안랩", 
    "263750": "펄어비스", "078340": "컴투스", "112040": "위메이드", "293490": "카카오게임즈", 
    "192080": "더블유게임즈", "251270": "넷마블", "036570": "엔씨소프트", "259960": "크래프톤",
    "005380": "현대차", "000270": "기아", "012330": "현대모비스", "011210": "현대위아", 
    "018880": "한온시스템", "161390": "한국타이어앤테크놀로지", "073240": "금호타이어", 
    "204320": "HL만도", "003490": "대한항공", "020560": "아시아나항공", "011200": "HMM", 
    "028670": "팬오션", "086280": "현대글로비스", "000120": "CJ대한통운", "012450": "한화에어로스페이스", 
    "047810": "한국항공우주", "079550": "LIG넥스원", "064350": "현대로템", "042660": "한화오션", 
    "329180": "HD현대중공업", "010140": "삼성중공업", "034020": "두산에너빌리티", "267250": "HD현대", 
    "082740": "HSD엔진", "272210": "한화시스템", "047820": "하림지주", "180640": "한진칼", "001800": "삼양홀딩스",
    "207940": "삼성바이오로직스", "068270": "셀트리온", "000100": "유한양행", "128940": "한미약품", 
    "006280": "녹십자", "069620": "대웅제약", "185750": "종근당", "009290": "광동제약", 
    "170900": "동아에스티", "068760": "셀트리온제약", "028300": "HLB", "196170": "알테오젠", 
    "145020": "휴젤", "086900": "메디톡스", "237690": "에스티팜", "141080": "리그켐바이오", 
    "143860": "케어젠", "096530": "씨젠", "091990": "셀트리온헬스케어",
    "373220": "LG에너지솔루션", "006400": "삼성SDI", "051910": "LG화학", "003670": "포스코퓨처엠", 
    "247540": "에코프로비엠", "086520": "에코프로", "066970": "엘앤에프", "096770": "SK이노베이션", 
    "010950": "S-Oil", "043260": "HD현대일렉트릭", "112610": "씨에스윈드", "009830": "한화솔루션", 
    "001570": "금양", "011170": "롯데케미칼", "011780": "금호석유", "377300": "카카오페이",
    "105560": "KB금융", "055550": "신한지주", "086790": "하나금융지주", "316140": "우리금융지주", 
    "024110": "기업은행", "138040": "메리츠금융지주", "032830": "삼성생명", "088350": "한화생명", 
    "082640": "동양생명", "001450": "현대해상", "005830": "DB손해보험", "000810": "삼성화재", 
    "006800": "미래에셋증권", "005940": "NH투자증권", "071050": "한국금융지주", "016360": "삼성증권", 
    "030200": "KT", "017670": "SK텔레콤", "032640": "LG유플러스",
    "005490": "POSCO홀딩스", "010130": "고려아연", "004020": "현대제철", "001230": "동국제강", 
    "103140": "풍산", "000670": "영풍", "001390": "KG케미칼", "300720": "한일시멘트", 
    "003410": "쌍용C&E", "015760": "한국전력", "036460": "한국가스공사", "071320": "지역난방공사", 
    "000720": "현대건설", "047040": "대우건설", "375500": "DL이앤씨", "006360": "GS건설",
    "097950": "CJ제일제당", "007310": "오뚜기", "004370": "농심", "003230": "삼양식품", 
    "000080": "하이트진로", "001680": "대상", "026960": "동서", "005610": "SPC삼립", 
    "090430": "아모레퍼시픽", "051900": "LG생활건강", "018250": "애경산업", "192820": "코스맥스", 
    "161890": "한국콜마", "004170": "신세계", "069960": "현대백화점", "023530": "롯데쇼핑", 
    "282330": "BGF리테일", "007070": "GS리테일", "139480": "이마트", "008770": "호텔신라", 
    "035250": "강원랜드", "039130": "하나투어", "080160": "모두투어", "352820": "하이브", 
    "035900": "JYP Ent.", "041510": "에스엠", "122870": "와이지엔터테인먼트", "035760": "CJ ENM", 
    "253450": "스튜디오드래곤", "033780": "KT&G", "021240": "코웨이", "003550": "LG", 
    "034730": "SK", "028260": "삼성물산", "000150": "두산", "047050": "포스코인터내셔널",
    "001040": "CJ", "078930": "GS", "000880": "한화", "006260": "LS", "004800": "효성",
    "004990": "롯데지주", "000210": "DL", "002020": "코오롱", "003240": "태광산업",
    "009540": "HD한국조선해양", "005250": "녹십자홀딩스", "011070": "LG이노텍", "002710": "TCC스틸",
    "010060": "OCI홀딩스", "019170": "신풍제약", "005385": "현대차우"
}

STOCK_SECTORS: dict[str, str] = {
    "005930": "반도체", "000660": "반도체", "035420": "플랫폼", "035720": "플랫폼",
    "018260": "IT서비스", "009150": "IT부품", "066570": "가전/IT", "034220": "가전/IT",
    "000990": "반도체", "042700": "반도체", "036930": "반도체", "240810": "반도체",
    "058470": "반도체", "357780": "IT소재", "039030": "반도체", "056190": "IT부품",
    "067310": "반도체", "005290": "IT소재", "012510": "소프트웨어", "053800": "소프트웨어",
    "263750": "게임", "078340": "게임", "112040": "게임", "293490": "게임",
    "192080": "게임", "251270": "게임", "036570": "게임", "259960": "게임",
    "005380": "자동차", "000270": "자동차", "012330": "자동차부품", "011210": "자동차부품",
    "018880": "자동차부품", "161390": "자동차부품", "073240": "자동차부품", "204320": "자동차부품",
    "003490": "항공", "020560": "항공", "011200": "해운", "028670": "해운",
    "086280": "물류", "000120": "물류", "012450": "방산/우주", "047810": "방산/우주",
    "079550": "방산", "064350": "방산/철도", "042660": "조선", "329180": "조선",
    "010140": "조선", "034020": "원자력/중공업", "082740": "선박엔진", "272210": "방산/IT",
    "207940": "바이오", "068270": "바이오", "000100": "제약", "128940": "제약",
    "006280": "제약", "069620": "제약", "185750": "제약", "009290": "제약",
    "170900": "제약", "068760": "바이오", "028300": "바이오", "196170": "바이오",
    "145020": "바이오", "086900": "바이오", "237690": "바이오", "141080": "바이오",
    "143860": "바이오", "096530": "바이오", "091990": "바이오", "019170": "제약",
    "373220": "2차전지", "006400": "2차전지", "051910": "배터리/화학", "003670": "2차전지소재",
    "247540": "2차전지소재", "086520": "2차전지소재", "066970": "2차전지소재", "096770": "에너지/화학",
    "010950": "정유", "043260": "전력인프라", "112610": "풍력에너지", "009830": "태양광/화학",
    "001570": "2차전지", "011170": "화학", "011780": "화학",
    "105560": "은행지주", "055550": "은행지주", "086790": "은행지주", "316140": "우리금융지주", 
    "024110": "기업은행", "138040": "메리츠금융지주", "032830": "삼성생명", "088350": "한화생명", 
    "082640": "동양생명", "001450": "현대해상", "005830": "DB손해보험", "000810": "삼성화재", 
    "006800": "미래에셋증권", "005940": "NH투자증권", "071050": "한국금융지주", "016360": "삼성증권", 
    "030200": "KT", "017670": "SK텔레콤", "032640": "LG유플러스",
    "005490": "POSCO홀딩스", "010130": "고려아연", "004020": "현대제철", "001230": "동국제강", 
    "103140": "풍산", "000670": "영풍", "001390": "KG케미칼", "300720": "한일시멘트", 
    "003410": "쌍용C&E", "015760": "한국전력", "036460": "한국가스공사", "071320": "지역난방공사", 
    "000720": "현대건설", "047040": "대우건설", "375500": "DL이앤씨", "006360": "GS건설",
    "097950": "CJ제일제당", "007310": "오뚜기", "004370": "농심", "003230": "삼양식품", 
    "000080": "하이트진로", "001680": "대상", "026960": "동서", "005610": "SPC삼립", 
    "090430": "아모레퍼시픽", "051900": "LG생활건강", "018250": "애경산업", "192820": "코스맥스", 
    "161890": "한국콜마", "004170": "신세계", "069960": "현대백화점", "023530": "롯데쇼핑", 
    "282330": "BGF리테일", "007070": "GS리테일", "139480": "이마트", "008770": "호텔신라", 
    "035250": "강원랜드", "039130": "하나투어", "080160": "모두투어", "352820": "하이브", 
    "035900": "JYP Ent.", "041510": "에스엠", "122870": "와이지엔터테인먼트", "035760": "CJ ENM", 
    "253450": "스튜디오드래곤", "033780": "KT&G", "021240": "코웨이", "003550": "LG", 
    "034730": "SK", "028260": "삼성물산", "000150": "두산", "047050": "포스코인터내셔널",
    "001040": "CJ", "078930": "GS", "000880": "한화", "006260": "LS", "004800": "효성",
    "004990": "롯데지주", "000210": "DL", "002020": "코오롱", "003240": "태광산업",
    "009540": "HD한국조선해양", "005250": "녹십자홀딩스", "011070": "LG이노텍", "002710": "TCC스틸",
    "010060": "OCI홀딩스", "019170": "신풍제약", "005385": "현대차우"
}

STOCK_SECTORS: dict[str, str] = {
    "005930": "반도체", "000660": "반도체", "035420": "플랫폼", "035720": "플랫폼",
    "018260": "IT서비스", "009150": "IT부품", "066570": "가전/IT", "034220": "가전/IT",
    "000990": "반도체", "042700": "반도체", "036930": "반도체", "240810": "반도체",
    "058470": "반도체", "357780": "IT소재", "039030": "반도체", "056190": "IT부품",
    "067310": "반도체", "005290": "IT소재", "012510": "소프트웨어", "053800": "소프트웨어",
    "263750": "게임", "078340": "게임", "112040": "게임", "293490": "게임",
    "192080": "게임", "251270": "게임", "036570": "게임", "259960": "게임",
    "005380": "자동차", "000270": "자동차", "012330": "자동차부품", "011210": "자동차부품",
    "018880": "자동차부품", "161390": "자동차부품", "073240": "자동차부품", "204320": "자동차부품",
    "003490": "항공", "020560": "항공", "011200": "해운", "028670": "해운",
    "086280": "물류", "000120": "물류", "012450": "방산/우주", "047810": "방산/우주",
    "079550": "방산", "064350": "방산/철도", "042660": "조선", "329180": "조선",
    "010140": "조선", "034020": "원자력/중공업", "082740": "선박엔진", "272210": "방산/IT",
    "207940": "바이오", "068270": "바이오", "000100": "제약", "128940": "제약",
    "006280": "제약", "069620": "제약", "185750": "제약", "009290": "제약",
    "170900": "제약", "068760": "바이오", "028300": "바이오", "196170": "바이오",
    "145020": "바이오", "086900": "바이오", "237690": "바이오", "141080": "바이오",
    "143860": "바이오", "096530": "바이오", "091990": "바이오", "019170": "제약",
    "373220": "2차전지", "006400": "2차전지", "051910": "배터리/화학", "003670": "2차전지소재",
    "247540": "2차전지소재", "086520": "2차전지소재", "066970": "2차전지소재", "096770": "에너지/화학",
    "010950": "정유", "043260": "전력인프라", "112610": "풍력에너지", "009830": "태양광/화학",
    "001570": "2차전지", "011170": "화학", "011780": "화학",
    "105560": "은행지주", "055550": "은행지주", "086790": "은행지주", "316140": "우리금융지주",
    "024110": "기업은행", "138040": "메리츠금융지주", "032830": "삼성생명", "088350": "한화생명",
    "082640": "동양생명", "001450": "현대해상", "005830": "DB손해보험", "000810": "삼성화재",
    "006800": "미래에셋증권", "005940": "NH투자증권", "071050": "한국금융지주", "016360": "삼성증권",
    "030200": "KT", "017670": "SK텔레콤", "032640": "LG유플러스",
    "005490": "POSCO홀딩스", "010130": "고려아연", "004020": "현대제철", "001230": "동국제강",
    "103140": "풍산", "000670": "영풍", "001390": "KG케미칼", "300720": "한일시멘트",
    "003410": "쌍용C&E", "015760": "한국전력", "036460": "한국가스공사", "071320": "지역난방공사",
    "000720": "현대건설", "047040": "대우건설", "375500": "DL이앤씨", "006360": "GS건설",
    "097950": "CJ제일제당", "007310": "오뚜기", "004370": "농심", "003230": "삼양식품",
    "000080": "하이트진로", "001680": "대상", "026960": "동서", "005610": "SPC삼립",
    "090430": "아모레퍼시픽", "051900": "LG생활건강", "018250": "애경산업", "192820": "코스맥스",
    "161890": "한국콜마", "004170": "신세계", "069960": "현대백화점", "023530": "롯데쇼핑",
    "282330": "BGF리테일", "007070": "GS리테일", "139480": "이마트", "008770": "호텔신라",
    "035250": "강원랜드", "039130": "하나투어", "080160": "모두투어", "352820": "하이브",
    "035900": "JYP Ent.", "041510": "에스엠", "122870": "와이지엔터테인먼트", "035760": "CJ ENM",
    "253450": "스튜디오드래곤", "033780": "KT&G", "021240": "코웨이", "003550": "LG",
    "034730": "SK", "028260": "삼성물산", "000150": "두산", "047050": "포스코인터내셔널",
    "001040": "CJ", "078930": "GS", "000880": "한화", "006260": "LS", "004800": "효성",
    "004990": "롯데지주", "000210": "DL", "002020": "코오롱", "003240": "태광산업",
    "009540": "HD한국조선해양", "005250": "녹십자홀딩스", "011070": "LG이노텍", "002710": "TCC스틸",
    "010060": "OCI홀딩스", "019170": "신풍제약", "005385": "현대차우"
}

KOSPI_UNIVERSE = [
    # 반도체/IT/빅테크
    "005930", "000660", "035420", "035720", "018260", "009150", "066570", 
    "034220", "000990", "042700", "036930", "240810", "058470", "357780", 
    "039030", "056190", "067310", "005290", "012510", "053800", "263750", 
    "078340", "112040", "293490", "192080", "251270", "036570", "259960",
    # 자동차/기계/조선/방산
    "005380", "000270", "012330", "011210", "018880", "161390", "073240", 
    "204320", "003490", "020560", "011200", "028670", "086280", "000120", 
    "012450", "047810", "079550", "064350", "042660", "329180", "010140", 
    "034020", "267250", "082740", "272210",
    # 바이오/헬스케어
    "207940", "068270", "000100", "128940", "006280", "069620", "185750", 
    "009290", "170900", "068760", "028300", "196170", "145020", "086900", 
    "237690", "141080", "143860", "096530", "091990",
    # 2차전지/배터리/화학/에너지
    "373220", "006400", "051910", "003670", "247540", "086520", "066970", 
    "096770", "010950", "043260", "034020", "112610", "009830", "001570", 
    "011170", "011780", "377300",
    # 금융/은행/카드/지주
    "105560", "055550", "086790", "316140", "024110", "138040", "032830", 
    "088350", "082640", "001450", "005830", "000810", "006800", "005940", 
    "071050", "016360", "030200", "017670", "032640",
    # 철강/소재/비철/건설
    "005490", "010130", "004020", "001230", "103140", "000670", "001390", 
    "300720", "003410", "015760", "036460", "071320", "000720", "047040", 
    "375500", "006360",
    # 유통/음식료/화장품/엔터/레저
    "097950", "007310", "004370", "003230", "000080", "001680", "026960", 
    "005610", "090430", "051900", "018250", "192820", "161890", "004170", 
    "069960", "023530", "282330", "007070", "139480", "008770", "035250", 
    "039130", "080160", "352820", "035900", "041510", "122870", "035760", 
    "253450", "033780", "021240", "003550", "034730", "028260", 
    "000150", "047050",
    # 추가 우량주 보강 (시총 상위 매칭)
    "001040", "078930", "000880", "006260", "004800",
    "004990", "000210", "002020", "003240", "009540",
    "005250", "011070", "002710", "010060", "019170",
    "005385", "047820", "180640", "001800"
]
KOSPI_UNIVERSE = list(dict.fromkeys(KOSPI_UNIVERSE))


def load_watchlist_data() -> dict:
    try:
        init_db()
        with connect_db() as conn:
            c = conn.execute("SELECT symbol FROM watchlist ORDER BY symbol ASC")
            symbols = [row[0] for row in c.fetchall()]
            
            # 종목 개수가 아예 비었을 때(0개)만 대표 우량주 5종목 자동 마이그레이션
            if len(symbols) == 0:
                default_symbols = ["005930", "000660", "035420", "005380", "035720"]
                ts = datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S")
                for s in default_symbols:
                    name = STOCK_NAMES.get(s, "우량 종목")
                    conn.execute(
                        "INSERT OR IGNORE INTO watchlist (symbol, name, created_at) VALUES (?, ?, ?)",
                        (s, name, ts)
                    )
                conn.commit()
                symbols = default_symbols
            
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


def save_daily_charts(symbol: str, data: list[dict]) -> None:
    """symbol에 해당하는 차트 목록을 daily_charts 테이블에 저장한다."""
    try:
        init_db()
        with connect_db() as conn:
            for row in data:
                date_str = row.get("date") or row.get("stck_bsop_date")
                # KIS API 날짜 포맷 'YYYYMMDD'을 'YYYY-MM-DD'로 규격화
                if date_str and len(date_str) == 8 and date_str.isdigit():
                    date_str = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"
                
                if not date_str:
                    continue
                
                open_val = float(row.get("open") or row.get("stck_opn_prpr") or 0.0)
                high_val = float(row.get("high") or row.get("stck_hgpr") or 0.0)
                low_val = float(row.get("low") or row.get("stck_lwpr") or 0.0)
                close_val = float(row.get("close") or row.get("stck_clpr") or row.get("stck_prpr") or 0.0)
                vol_val = float(row.get("volume") or row.get("acml_vol") or 0.0)
                
                conn.execute(
                    """
                    INSERT OR REPLACE INTO daily_charts (symbol, date, open, high, low, close, volume)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (symbol, date_str, open_val, high_val, low_val, close_val, vol_val)
                )
            conn.commit()
    except Exception as e:
        logger.warning(f"Failed to save daily charts for {symbol} to DB: {e}")


def load_daily_charts(symbol: str, limit: int = 120) -> list[dict]:
    """symbol에 해당하는 일별 차트 데이터를 날짜 정렬하여 로드한다."""
    try:
        init_db()
        with connect_db() as conn:
            c = conn.execute(
                """
                SELECT date, open, high, low, close, volume 
                FROM daily_charts 
                WHERE symbol = ? 
                ORDER BY date ASC
                """,
                (symbol,)
            )
            rows = c.fetchall()
            charts = []
            for r in rows:
                charts.append({
                    "date": r[0],
                    "open": r[1],
                    "high": r[2],
                    "low": r[3],
                    "close": r[4],
                    "volume": r[5]
                })
            if len(charts) > limit:
                charts = charts[-limit:]
            return charts
    except Exception as e:
        logger.warning(f"Failed to load daily charts for {symbol} from DB: {e}")
        return []


def get_watchlist_extra_info(symbol: str) -> dict:
    """관심종목의 최신 분석 점수, 이유, 현재가, 거래량, 등락률, RSI, 갱신시각, 이평선 추세를 DB 캐시에서 조회해 반환한다."""
    init_db()
    res = {
        "score": None,
        "reason": "분석 정보 없음",
        "price": None,
        "volume": None,
        "change_rate": None,
        "rsi": None,
        "updated_at": None,
        "sma_trend": "데이터 없음"
    }
    try:
        with connect_db() as conn:
            # 1. scanned_candidates 테이블에서 최신 스코어, 이유, 가격, RSI, 갱신시각 조회
            c_cand = conn.execute(
                """
                SELECT score, reasons, price, rsi, scanned_at 
                FROM scanned_candidates 
                WHERE symbol = ? 
                ORDER BY scanned_at DESC 
                LIMIT 1
                """,
                (symbol,)
            )
            row_cand = c_cand.fetchone()
            if row_cand:
                res["score"] = row_cand[0]
                res["reason"] = row_cand[1] or "조건 미지정"
                res["price"] = row_cand[2]
                res["rsi"] = row_cand[3]
                res["updated_at"] = row_cand[4]
                
            # 2. daily_charts 테이블에서 최신 가격, 전일 대비 등락률, 거래량 조회
            c_chart = conn.execute(
                """
                SELECT close, volume, date 
                FROM daily_charts 
                WHERE symbol = ? 
                ORDER BY date DESC 
                LIMIT 2
                """,
                (symbol,)
            )
            rows_chart = c_chart.fetchall()
            if rows_chart:
                latest_chart = rows_chart[0]
                if res["price"] is None:
                    res["price"] = latest_chart[0]
                res["volume"] = latest_chart[1]
                if res["updated_at"] is None:
                    res["updated_at"] = latest_chart[2]
                
                # 등락률 계산
                if len(rows_chart) >= 2:
                    curr_close = rows_chart[0][0]
                    prev_close = rows_chart[1][0]
                    if prev_close > 0:
                        res["change_rate"] = round(((curr_close - prev_close) / prev_close) * 100, 2)
                        
            # 3. 이동평균 상태 계산 (SMA20 vs SMA60)
            c_ma = conn.execute(
                """
                SELECT close 
                FROM daily_charts 
                WHERE symbol = ? 
                ORDER BY date DESC 
                LIMIT 60
                """,
                (symbol,)
            )
            rows_ma = [r[0] for r in c_ma.fetchall()]
            if len(rows_ma) >= 60:
                rows_ma.reverse()  # 오래된 순 정렬
                sma20 = sum(rows_ma[-20:]) / 20
                sma60 = sum(rows_ma[-60:]) / 60
                curr_price = rows_ma[-1]
                
                if sma20 > sma60:
                    if curr_price > sma20:
                        res["sma_trend"] = "정배열 (상승)"
                    else:
                        res["sma_trend"] = "정배열 (조정)"
                else:
                    if curr_price > sma20:
                        res["sma_trend"] = "반등 시도"
                    else:
                        res["sma_trend"] = "역배열 (하락)"
            elif len(rows_ma) >= 20:
                rows_ma.reverse()
                sma20 = sum(rows_ma[-20:]) / 20
                curr_price = rows_ma[-1]
                if curr_price > sma20:
                    res["sma_trend"] = "20일선 위"
                else:
                    res["sma_trend"] = "20일선 아래"
            else:
                res["sma_trend"] = "자료 부족"
    except Exception as e:
        logger.warning(f"Failed to get watchlist extra info for {symbol}: {e}")
    return res
