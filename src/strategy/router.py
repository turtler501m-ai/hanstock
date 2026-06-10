import json
from src.config import config
from src.utils.logger import logger
from src.db.repository import save_trade, save_decision_log
from src.api.kis_api import KIStockAPI

class OrderRouter:
    def __init__(self, api: KIStockAPI):
        self.api = api
        self.dry_run = config.dry_run
        self.env = config.trading_env
        self.enable_live = config.enable_live_trading
        self.require_approval = config.require_approval
        
        self.real_orders_enabled = (not self.dry_run) and self.env == "real" and self.enable_live
        self.submission_enabled = (not self.dry_run) and (self.env == "demo" or self.real_orders_enabled)

    def _current_holding_qty(self, symbol: str) -> int:
        try:
            balance = self.api.get_balance()
        except Exception:
            return 0
        for holding in balance.get("output1", []) or []:
            if str(holding.get("pdno") or "") == str(symbol):
                try:
                    return int(float(holding.get("hldg_qty") or 0))
                except (TypeError, ValueError):
                    return 0
        return 0

    def route(self, symbol: str, name: str, action: str, qty: int, price: int, reason: str, indicators: dict, strategy_id: str = None) -> dict:
        # Decision Log 기록
        save_decision_log(symbol, name, action, qty, price, reason, indicators, True)
        
        if not self.submission_enabled:
            logger.info(f"[ROUTER] Paper Trading: {action} {name} qty={qty}")
            save_trade(symbol, name, action, qty, price, reason, True, False, strategy_id=strategy_id)
            return {"ok": True, "msg": "Paper trading executed", "status": "paper"}

        if self.require_approval:
            # 대기열(approvals)에 넣기
            approval_id = self._insert_approval(symbol, name, action, qty, price, reason, strategy_id=strategy_id)
            logger.info(f"[ROUTER] Pending Approval: {action} {name} qty={qty}")
            return {"ok": True, "msg": "Added to approval queue", "status": "pending", "approval_id": approval_id}
            
        # 직접 KIS API 호출
        pre_order_qty = self._current_holding_qty(symbol)
        result = self.api.place_order(symbol, action, price, qty)
        ok = result.get("rt_cd") == "0"
        logger.info(f"[ROUTER] Live Execution {'OK' if ok else 'FAILED'}: {result.get('msg1', '')}")
        save_trade(
            symbol,
            name,
            action,
            qty,
            price,
            reason,
            ok,
            True,
            broker_result=result,
            order_status="submitted" if ok else "failed",
            response_msg=str(result.get("msg1", "")),
            filled_qty=0,
            filled_price=0,
            pre_order_qty=pre_order_qty,
            strategy_id=strategy_id,
        )
        return {"ok": ok, "msg": result.get("msg1", ""), "status": "live"}

    def _insert_approval(self, symbol: str, name: str, action: str, qty: int, price: int, reason: str, strategy_id: str = None) -> int | None:
        from src.db.repository import connect_db
        from datetime import datetime, timezone, timedelta
        
        KST = timezone(timedelta(hours=9))
        now = datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S")
        
        try:
            with connect_db() as conn:
                conn.execute("""
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
                """)
                # Ensure strategy_id column exists
                try:
                    from src.db.repository import _ensure_column
                    _ensure_column(conn, "approvals", "strategy_id", "TEXT")
                except Exception:
                    pass
                cursor = conn.execute(
                    """
                    INSERT INTO approvals
                    (created_at, updated_at, symbol, name, action, qty, price, reason, source, status, response_msg, strategy_id)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', '', ?)
                    """,
                    (now, now, symbol, name, action, qty, price, reason, 'auto_trader', strategy_id),
                )
                return cursor.lastrowid
        except Exception as e:
            logger.error(f"[ROUTER] Failed to insert approval: {e}")
            return None
