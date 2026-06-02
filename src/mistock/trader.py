from __future__ import annotations

import json
from typing import Any

from src.mistock.config import config
from src.mistock import db
from src.mistock.strategy import NASDAQ_UNIVERSE, fetch_history, normalize_symbol, quote, strategy_profile, symbol_name


def runtime_flags() -> dict[str, Any]:
    order_submission_enabled = (not config.dry_run) and config.trading_env == "paper"
    return {
        "trading_env": config.trading_env,
        "dry_run": config.dry_run,
        "enable_live_trading": config.enable_live_trading,
        "require_approval": config.require_approval,
        "order_submission_enabled": order_submission_enabled,
        "real_orders_enabled": False,
    }


def get_watchlist() -> list[dict[str, Any]]:
    return db.rows("SELECT symbol, name, created_at FROM watchlist ORDER BY symbol")


def add_watchlist(symbol: str, name: str | None = None) -> dict[str, Any]:
    symbol = normalize_symbol(symbol)
    if not symbol:
        raise ValueError("symbol is required")
    item_name = name or symbol_name(symbol)
    db.execute(
        "INSERT OR IGNORE INTO watchlist (symbol, name, created_at) VALUES (?, ?, ?)",
        (symbol, item_name, db.now_text()),
    )
    return {"symbol": symbol, "name": item_name}


def delete_watchlist(symbol: str) -> None:
    db.execute("DELETE FROM watchlist WHERE symbol = ?", (normalize_symbol(symbol),))


def get_holdings() -> list[dict[str, Any]]:
    holdings = []
    for row in db.rows("SELECT symbol, name, qty, avg_price FROM holdings ORDER BY symbol"):
        q = quote(row["symbol"])
        price = float(q["current"] or row["avg_price"] or 0.0)
        qty = float(row["qty"] or 0.0)
        avg = float(row["avg_price"] or 0.0)
        value = qty * price
        pnl = (price - avg) * qty
        rt = ((price - avg) / avg * 100.0) if avg > 0 else 0.0
        holdings.append({
            "symbol": row["symbol"],
            "name": row["name"],
            "qty": qty,
            "price": price,
            "avg_price": avg,
            "value": value,
            "pnl": pnl,
            "rt": rt,
        })
    return holdings


def get_balance() -> dict[str, Any]:
    cash = float(db.get_setting("cash", str(config.total_capital)) or 0.0)
    holdings = get_holdings()
    stock_eval = sum(float(item["value"] or 0.0) for item in holdings)
    pnl = sum(float(item["pnl"] or 0.0) for item in holdings)
    total_eval = cash + stock_eval
    return {
        "cash": cash,
        "total_eval": total_eval,
        "broker_total_eval": total_eval,
        "calculated_total_eval": total_eval,
        "stock_eval": stock_eval,
        "cash_ratio": cash / total_eval if total_eval > 0 else 0.0,
        "stock_ratio": stock_eval / total_eval if total_eval > 0 else 0.0,
        "pnl": pnl,
        "holdings": holdings,
    }


def scan_candidates(min_score: int = 2, limit: int | None = None) -> dict[str, Any]:
    watchlist = [item["symbol"] for item in get_watchlist()]
    universe = list(dict.fromkeys(watchlist + NASDAQ_UNIVERSE))[: limit or config.scan_universe_size]
    candidates = []
    scanned = 0
    scan_error = ""
    for symbol in universe:
        try:
            hist = fetch_history(symbol)
            profile = strategy_profile(hist["close"], hist["high"], hist["volume"])
            scanned += 1
            score = float(profile["score"])
            row = {
                "ticker": symbol,
                "symbol": symbol,
                "name": symbol_name(symbol),
                "score": score,
                "reasons": profile["reasons"],
                "price": profile["price"],
                "rsi": profile["rsi"],
                "rsi2": profile["rsi2"],
                "macd_hist": profile["macd_hist"],
                "sma20": profile["sma20"],
                "sma60": profile["sma60"],
            }
            db.execute(
                """
                INSERT INTO scanned_candidates
                (scanned_at, symbol, name, score, reasons, price, env, rsi, rsi2, macd_hist, sma20, sma60)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    db.now_text(), symbol, row["name"], score, ",".join(profile["reasons"]),
                    row["price"], config.trading_env, row["rsi"], row["rsi2"], row["macd_hist"], row["sma20"], row["sma60"],
                ),
            )
            if score >= min_score:
                candidates.append(row)
        except Exception as exc:
            scan_error = str(exc)
    candidates.sort(key=lambda item: (item["score"], item["price"] or 0), reverse=True)
    return {
        "candidates": candidates,
        "scanned": scanned,
        "min_score": min_score,
        "scan_summary": {"scanned": scanned, "matched": len(candidates), "scan_error": scan_error},
        "scan_error": scan_error,
    }


def build_orders(candidates: list[dict[str, Any]], cash: float) -> list[dict[str, Any]]:
    orders = []
    budget = max(0.0, cash * (1.0 - config.cash_buffer))
    slots = max(1, min(config.max_positions, len(candidates)))
    per_order = budget / slots if slots else 0.0
    for candidate in candidates[:slots]:
        price = float(candidate.get("price") or quote(candidate["symbol"])["current"] or 0.0)
        if price <= 0:
            continue
        qty = int(per_order // price)
        if qty <= 0:
            continue
        orders.append({
            "ticker": candidate["symbol"],
            "symbol": candidate["symbol"],
            "name": candidate["name"],
            "limit_price": price,
            "price": price,
            "quantity": qty,
            "qty": qty,
            "estimated_cost": qty * price,
            "reason": ", ".join(candidate.get("reasons") or []),
            "strategy_score": candidate.get("score", 0),
        })
    return orders


def signals() -> list[dict[str, Any]]:
    balance = get_balance()
    rows = []
    for holding in balance["holdings"]:
        hist = fetch_history(holding["symbol"])
        profile = strategy_profile(hist["close"], hist["high"], hist["volume"])
        action = "hold"
        if profile["rsi"] >= config.rsi_sell or holding["rt"] >= config.take_profit:
            action = "sell"
        elif holding["rt"] <= config.stop_loss_pct:
            action = "sell"
        rows.append({
            "symbol": holding["symbol"],
            "name": holding["name"],
            "action": action,
            "strategy_score": profile["score"],
            "signal_qty": int(holding["qty"]),
            "signal_price": holding["price"],
            "rsi": profile["rsi"],
            "rsi2": profile["rsi2"],
            "macd_hist": profile["macd_hist"],
            "reason": ", ".join(profile["reasons"]),
        })
    return rows


def execution_plan() -> dict[str, Any]:
    balance = get_balance()
    scan = scan_candidates()
    orders = build_orders(scan["candidates"], balance["cash"])
    return {
        "mode": "mistock-paper",
        "plan": orders,
        "cash": balance["cash"],
        "remaining_cash": balance["cash"] - sum(item["estimated_cost"] for item in orders),
        "total_eval": balance["total_eval"],
        "pnl": balance["pnl"],
        "daily_loss_halt": False,
        "scanned": scan["scanned"],
        "scan_error": scan["scan_error"],
    }


def place_paper_order(symbol: str, action: str, qty: float, price: float, reason: str = "") -> dict[str, Any]:
    symbol = normalize_symbol(symbol)
    action = str(action).lower()
    qty = float(qty)
    price = float(price or quote(symbol)["current"] or 0.0)
    if qty <= 0 or price <= 0:
        return {"ok": False, "status": "failed", "message": "qty and price must be greater than 0"}
    cash = float(db.get_setting("cash", str(config.total_capital)) or 0.0)
    existing = db.row("SELECT symbol, name, qty, avg_price FROM holdings WHERE symbol = ?", (symbol,))
    if action == "buy":
        cost = qty * price
        if cost > cash:
            return {"ok": False, "status": "failed", "message": "insufficient paper cash"}
        if existing:
            old_qty = float(existing["qty"])
            old_avg = float(existing["avg_price"])
            new_qty = old_qty + qty
            new_avg = ((old_qty * old_avg) + cost) / new_qty
            db.execute("UPDATE holdings SET qty = ?, avg_price = ?, updated_at = ? WHERE symbol = ?", (new_qty, new_avg, db.now_text(), symbol))
        else:
            db.execute(
                "INSERT INTO holdings (symbol, name, qty, avg_price, updated_at) VALUES (?, ?, ?, ?, ?)",
                (symbol, symbol_name(symbol), qty, price, db.now_text()),
            )
        db.set_setting("cash", str(cash - cost))
    elif action == "sell":
        if not existing or float(existing["qty"]) < qty:
            return {"ok": False, "status": "failed", "message": "insufficient paper holdings"}
        remaining = float(existing["qty"]) - qty
        if remaining > 0:
            db.execute("UPDATE holdings SET qty = ?, updated_at = ? WHERE symbol = ?", (remaining, db.now_text(), symbol))
        else:
            db.execute("DELETE FROM holdings WHERE symbol = ?", (symbol,))
        db.set_setting("cash", str(cash + qty * price))
    else:
        return {"ok": False, "status": "failed", "message": "action must be buy or sell"}
    save_trade(symbol, symbol_name(symbol), action, qty, price, reason, True, "filled", "paper order filled")
    return {"ok": True, "status": "filled", "msg1": "paper order filled"}


def save_trade(symbol: str, name: str, action: str, qty: float, price: float, reason: str, ok: bool, order_status: str, response_msg: str) -> None:
    db.execute(
        """
        INSERT INTO trades (ts, symbol, name, action, qty, price, reason, ok, env, dry_run, order_status, response_msg, broker_result)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            db.now_text(), symbol, name, action, qty, price, reason, int(ok), config.trading_env,
            int(config.dry_run), order_status, response_msg, json.dumps({"paper": True}, ensure_ascii=False),
        ),
    )

