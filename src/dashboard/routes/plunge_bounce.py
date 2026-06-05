# -*- coding: utf-8 -*-
import sqlite3
import threading
from datetime import datetime
from fastapi import Body, HTTPException, Request
from fastapi.responses import FileResponse

from src.dashboard.core import (
    app,
    WEB_DIR,
    _scheduler_running_lock,
    _scheduler_run_state,
    _bg_run_scheduled_cycle,
)
from src import trader
from src.utils.logger import logger

@app.get("/plunge-bounce", response_class=FileResponse)
def read_plunge_bounce_dashboard():
    """Renders the plunge bounce strategy dashboard page."""
    return FileResponse(WEB_DIR / "templates" / "plunge_bounce.html")


@app.get("/api/strategy/plunge_bounce/performance")
def get_strategy_performance():
    """Calculates daily, monthly, and overall performance for plunge_bounce_strategy."""
    try:
        trades = []
        with trader.connect_db() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM trades WHERE strategy_id = 'plunge_bounce_strategy' AND ok = 1 ORDER BY ts ASC"
            ).fetchall()
            trades = [dict(row) for row in rows]

        holdings = {}
        realized_pnl = 0.0
        winning_trades = 0
        losing_trades = 0
        pnl_by_date = {}   # {date_str: cumulative_pnl}
        pnl_by_month = {}  # {month_str: realized_pnl}
        total_sell_trades = 0

        for t in trades:
            symbol = t["symbol"]
            qty = t["qty"]
            price = t["price"]
            action = t["action"]
            date_str = t["ts"][:10]  # "YYYY-MM-DD"
            month_str = t["ts"][:7]  # "YYYY-MM"

            if symbol not in holdings:
                holdings[symbol] = {"qty": 0, "cost": 0.0}

            if action == "buy":
                current_qty = holdings[symbol]["qty"]
                new_qty = current_qty + qty
                if new_qty > 0:
                    holdings[symbol]["cost"] = (
                        (current_qty * holdings[symbol]["cost"]) + (qty * price)
                    ) / new_qty
                holdings[symbol]["qty"] = new_qty
            elif action == "sell":
                current_qty = holdings[symbol]["qty"]
                sell_qty = min(qty, current_qty)
                if sell_qty > 0:
                    profit = (price - holdings[symbol]["cost"]) * sell_qty
                    realized_pnl += profit
                    pnl_by_month[month_str] = pnl_by_month.get(month_str, 0.0) + profit
                    total_sell_trades += 1
                    if profit > 0:
                        winning_trades += 1
                    elif profit < 0:
                        losing_trades += 1

                    holdings[symbol]["qty"] -= sell_qty
                    if holdings[symbol]["qty"] <= 0:
                        holdings[symbol]["qty"] = 0
                        holdings[symbol]["cost"] = 0.0
            
            pnl_by_date[date_str] = realized_pnl

        # Calculate metrics
        total_trades = len(trades)
        win_rate = (winning_trades / total_sell_trades * 100) if total_sell_trades > 0 else 0
        avg_profit = (realized_pnl / total_sell_trades) if total_sell_trades > 0 else 0

        # Format charts series
        daily_pnl_list = [
            {"date": d, "pnl": round(pnl, 2)}
            for d, pnl in sorted(pnl_by_date.items())
        ]
        monthly_pnl_list = [
            {"month": m, "pnl": round(pnl, 2)}
            for m, pnl in sorted(pnl_by_month.items())
        ]

        return {
            "ok": True,
            "metrics": {
                "total_trades": total_trades,
                "sell_trades": total_sell_trades,
                "winning_trades": winning_trades,
                "losing_trades": losing_trades,
                "win_rate": round(win_rate, 2),
                "realized_pnl": round(realized_pnl, 2),
                "avg_profit_per_trade": round(avg_profit, 2),
            },
            "daily_pnl": daily_pnl_list,
            "monthly_pnl": monthly_pnl_list,
            "trades": trades[::-1],  # latest first
        }
    except Exception as e:
        logger.error(f"[PlungeBounceRoute] Performance calculation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/strategy/plunge_bounce/scan")
def run_plunge_bounce_scan():
    """Triggers real-time scanning of the KOSPI_UNIVERSE and Watchlist using PlungeBounceStrategy."""
    try:
        from src.trader import KIStockAPI
        api = KIStockAPI()

        from src.strategy.seven_split import build_scan_universe, find_candidates, WATCHLIST, KOSPI_UNIVERSE

        # 1. Fetch currently held symbols to exclude them from the scan
        balance = api.get_balance()
        stocks = balance.get("output1", []) or []
        held_symbols = {s.get("pdno", "") for s in stocks}

        # 2. Build full universe list (WATCHLIST + KOSPI_UNIVERSE)
        full_universe = list(dict.fromkeys(WATCHLIST + KOSPI_UNIVERSE))
        scan_list = [code for code in full_universe if code not in held_symbols]

        # 3. Perform scan forcing the plunge_bounce_strategy custom rule
        logger.info(f"[PlungeBounceRoute] Real-time scan initiated for {len(scan_list)} symbols")
        scan_result = find_candidates(
            held_symbols,
            universe=scan_list,
            min_score=1.0,  # score 5.0 is passed, 0.0 is skipped
            ranker="rule_only",
            api=api,
            strategy_model="plunge_bounce_strategy",
        )

        candidates = scan_result.get("candidates", [])
        scan_summary = scan_result.get("scan_summary", [])

        # Sort summary to show highest-scoring or lowest-disparity first
        # Filter details out to make it light
        summary_clean = []
        for s in scan_summary:
            summary_clean.append({
                "symbol": s.get("ticker"),
                "name": s.get("name"),
                "price": s.get("current_price"),
                "score": s.get("score"),
                "reasons": s.get("reasons"),
                "rsi": s.get("rsi"),
                "rsi2": s.get("rsi2"),
                "sma20": s.get("sma20"),
                "bb_lo": s.get("bb_lo"),
            })

        return {
            "ok": True,
            "candidates": candidates,
            "scan_summary": summary_clean,
            "scanned_count": len(scan_summary),
            "candidates_count": len(candidates),
        }
    except Exception as e:
        logger.error(f"[PlungeBounceRoute] Scan failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/strategy/plunge_bounce/run-trader")
def run_plunge_bounce_trader(payload: dict = Body(...)):
    """Locks plunge_bounce_strategy as the active model and triggers an execution run cycle in the background."""
    global _scheduler_run_state
    mode = str(payload.get("mode", "execute")).lower()
    
    # 1. Update DB to set plunge_bounce_strategy as the active selected strategy
    from src.db.repository import connect_db
    try:
        with connect_db() as conn:
            conn.execute("UPDATE ai_strategies SET selected = 0")
            conn.execute(
                "UPDATE ai_strategies SET selected = 1 WHERE id = 'plunge_bounce_strategy'"
            )
        logger.info("[PlungeBounceRoute] Set plunge_bounce_strategy as active selected model.")
    except Exception as e:
        logger.error(f"[PlungeBounceRoute] Failed to update selected strategy in DB: {e}")

    include_ai_rebalance = False
    auto_approve = bool(payload.get("auto_approve", True))

    # 2. Trigger scheduler in background thread
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
        daemon=True,
    )
    t.start()
    return {"status": "started", "mode": mode}
