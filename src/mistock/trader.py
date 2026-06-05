from __future__ import annotations

import json
from typing import Any

from src.mistock.config import config
from src.mistock import db
from src.mistock.strategy import NASDAQ_UNIVERSE, fetch_history, normalize_symbol, quote, strategy_profile, symbol_name


_kis_client_cache = None


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return default


def _first_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, list):
        return next((item for item in value if isinstance(item, dict)), {})
    return {}


def _first_positive(mapping: dict[str, Any], keys: list[str]) -> float:
    for key in keys:
        value = _to_float(mapping.get(key))
        if value > 0:
            return value
    return 0.0


def _holdings_from_overseas_balance(balance_data: dict[str, Any]) -> list[dict[str, Any]]:
    if not isinstance(balance_data, dict):
        from src.utils.logger import logger
        logger.error(f"Invalid balance_data type in get_holdings: {type(balance_data)}, expected dict. Value: {balance_data}")
        balance_data = {"output1": [], "output2": {}, "output3": {}}

    output1 = balance_data.get("output1", [])
    if not isinstance(output1, list):
        output1 = [output1] if isinstance(output1, dict) else []

    holdings = []
    for item in output1:
        if not isinstance(item, dict):
            continue
        symbol = str(item.get("pdno", "")).strip()
        if not symbol:
            continue
        name = item.get("prdt_name", symbol)
        qty = _to_float(item.get("cblc_qty13") or item.get("cblc_qty"))
        if qty <= 0:
            continue
        avg = _to_float(item.get("avg_unpr3") or item.get("avg_unpr"))
        price = _to_float(item.get("ovrs_now_pric1") or item.get("ovrs_now_pric"))
        if price <= 0:
            price = _to_float(quote(symbol).get("current"))
        value = _to_float(item.get("frcr_evlu_amt2") or item.get("frcr_evlu_amt"), qty * price)
        pnl = _to_float(item.get("evlu_pfls_amt2") or item.get("evlu_pfls_amt"), (price - avg) * qty)
        rt = _to_float(
            item.get("evlu_pfls_rt1") or item.get("evlu_pfls_rt"),
            ((price - avg) / avg * 100.0) if avg > 0 else 0.0,
        )
        holdings.append({
            "symbol": symbol,
            "name": name,
            "qty": qty,
            "price": price,
            "avg_price": avg,
            "value": value,
            "pnl": pnl,
            "rt": rt,
        })
    return holdings


def _get_kis_client():
    global _kis_client_cache
    if _kis_client_cache is None:
        from src.kis_client import KISClient, KISClientConfig
        from src.config import config as main_config
        from src.api.kis_api import HTTP
        from pathlib import Path
        env = config.trading_env
        if env not in {"demo", "real"}:
            env = "demo"
        base_url = "https://openapi.koreainvestment.com:9443" if env == "real" else "https://openapivts.koreainvestment.com:29443"
        client_config = KISClientConfig(
            base_url=base_url,
            app_key=main_config.kistock_app_key,
            app_secret=main_config.kistock_app_secret,
            account_no=main_config.kistock_account,
            trading_env=env,
            token_cache_path=Path("data") / "kis_token.json",
        )
        _kis_client_cache = KISClient(client_config, session=HTTP)
    return _kis_client_cache

def runtime_flags() -> dict[str, Any]:
    real_orders_enabled = (not config.dry_run) and config.trading_env == "real" and config.enable_live_trading
    order_submission_enabled = (not config.dry_run) and (config.trading_env in {"paper", "demo"} or real_orders_enabled)
    return {
        "trading_env": config.trading_env,
        "dry_run": config.dry_run,
        "enable_live_trading": config.enable_live_trading,
        "require_approval": config.require_approval,
        "order_submission_enabled": order_submission_enabled,
        "real_orders_enabled": real_orders_enabled,
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
    if config.trading_env not in {"demo", "real"}:
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
    else:
        try:
            client = _get_kis_client()
            balance_data = client.get_overseas_balance()
            return _holdings_from_overseas_balance(balance_data)
        except Exception as e:
            from src.utils.logger import logger
            logger.error(f"Failed to fetch KIS US holdings: {e}")
            return []


def get_balance() -> dict[str, Any]:
    if config.trading_env not in {"demo", "real"}:
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
    else:
        try:
            client = _get_kis_client()
            balance_data = client.get_overseas_balance()
            if not isinstance(balance_data, dict):
                from src.utils.logger import logger
                logger.error(f"Invalid balance_data type in get_balance: {type(balance_data)}, expected dict. Value: {balance_data}")
                balance_data = {"output1": [], "output2": {}, "output3": {}}
            
            summary = balance_data.get("output2", {})
            if not isinstance(summary, dict):
                if isinstance(summary, list):
                    summary = next((item for item in summary if isinstance(item, dict)), {})
                else:
                    summary = {}
            
            # KIS 외화 예수금 파싱
            cash = _first_positive(summary, [
                "frcr_dncl_amt",
                "frcr_dncl_amt_2",
                "frcr_buy_amt_smtl",
                "frcr_drwg_psbl_amt",
                "frcr_drwg_psbl_amt_1",
            ])
            
            # 통합증거금 원화 가용 자원 파싱 및 합산
            output3 = balance_data.get("output3", {})
            if not isinstance(output3, dict):
                if isinstance(output3, list):
                    output3 = next((item for item in output3 if isinstance(item, dict)), {})
                else:
                    output3 = {}
                    
            exchange_rate = _to_float(summary.get("frst_rt") or output3.get("frst_rt"), 1380.0)
            if exchange_rate <= 0:
                exchange_rate = 1380.0
                
            krw_cash = _first_positive(output3, ["tot_dncl_amt", "dncl_amt"])
            if krw_cash > 0:
                # 98% 마진율을 적용해 달러 가용 금액에 합산 (통합증거금)
                cash += (krw_cash / exchange_rate) * 0.98

            holdings = _holdings_from_overseas_balance(balance_data)
            stock_eval = sum(float(item["value"] or 0.0) for item in holdings)
            pnl = sum(float(item["pnl"] or 0.0) for item in holdings)
            broker_total_eval = _first_positive(summary, [
                "tot_asst_amt",
                "tot_evlu_amt",
                "frcr_evlu_tota",
            ]) or _first_positive(output3, [
                "tot_asst_amt",
                "tot_evlu_amt",
                "evlu_amt_smtl",
                "frcr_evlu_tota",
            ])
            if cash <= 0 and broker_total_eval > stock_eval:
                cash = broker_total_eval - stock_eval
            total_eval = cash + stock_eval
            return {
                "cash": cash,
                "total_eval": total_eval,
                "broker_total_eval": broker_total_eval or total_eval,
                "calculated_total_eval": total_eval,
                "stock_eval": stock_eval,
                "cash_ratio": cash / total_eval if total_eval > 0 else 0.0,
                "stock_ratio": stock_eval / total_eval if total_eval > 0 else 0.0,
                "pnl": pnl,
                "holdings": holdings,
            }
        except Exception as e:
            from src.utils.logger import logger
            logger.error(f"Failed to fetch KIS US balance: {e}")
            return {
                "cash": 0.0,
                "total_eval": 0.0,
                "broker_total_eval": 0.0,
                "calculated_total_eval": 0.0,
                "stock_eval": 0.0,
                "cash_ratio": 0.0,
                "stock_ratio": 0.0,
                "pnl": 0.0,
                "holdings": [],
                "_error": str(e),
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


def notify_slack_order(symbol: str, action: str, qty: float, price: float, reason: str, ok: bool) -> None:
    try:
        from src.notifier.slack import mistock_slack_order
        # Gather indicators
        indicators = {"rsi": 0.0, "sma20": 0.0, "sma60": 0.0, "rt": 0.0}
        try:
            hist = fetch_history(symbol)
            profile = strategy_profile(hist["close"], hist["high"], hist["volume"])
            indicators["rsi"] = float(profile.get("rsi", 0.0))
            indicators["sma20"] = float(profile.get("sma20", 0.0))
            indicators["sma60"] = float(profile.get("sma60", 0.0))
        except Exception:
            pass

        if action == "sell":
            try:
                if config.trading_env not in {"demo", "real"}:
                    existing = db.row("SELECT avg_price FROM holdings WHERE symbol = ?", (symbol,))
                    if existing:
                        avg_price = float(existing["avg_price"])
                        indicators["rt"] = ((price - avg_price) / avg_price * 100.0) if avg_price > 0 else 0.0
                else:
                    holdings = get_holdings()
                    matching = next((h for h in holdings if h["symbol"] == symbol), None)
                    if matching:
                        indicators["rt"] = matching["rt"]
            except Exception:
                pass

        mistock_slack_order(
            name=symbol_name(symbol),
            symbol=symbol,
            action=action,
            qty=qty,
            price=price,
            reason=reason,
            ok=ok,
            indicators=indicators,
        )
    except Exception as e:
        from src.utils.logger import logger
        logger.error(f"Failed to send Slack order notification: {e}")


def place_paper_order(symbol: str, action: str, qty: float, price: float, reason: str = "") -> dict[str, Any]:
    symbol = normalize_symbol(symbol)
    action = str(action).lower()
    qty = float(qty)
    price = float(price or quote(symbol)["current"] or 0.0)
    if qty <= 0 or price <= 0:
        notify_slack_order(symbol, action, qty, price, "qty and price must be greater than 0", False)
        return {"ok": False, "status": "failed", "message": "qty and price must be greater than 0"}

    if config.trading_env not in {"demo", "real"}:
        cash = float(db.get_setting("cash", str(config.total_capital)) or 0.0)
        existing = db.row("SELECT symbol, name, qty, avg_price FROM holdings WHERE symbol = ?", (symbol,))
        if action == "buy":
            cost = qty * price
            if cost > cash:
                notify_slack_order(symbol, action, qty, price, "insufficient paper cash", False)
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
                notify_slack_order(symbol, action, qty, price, "insufficient paper holdings", False)
                return {"ok": False, "status": "failed", "message": "insufficient paper holdings"}
            remaining = float(existing["qty"]) - qty
            if remaining > 0:
                db.execute("UPDATE holdings SET qty = ?, updated_at = ? WHERE symbol = ?", (remaining, db.now_text(), symbol))
            else:
                db.execute("DELETE FROM holdings WHERE symbol = ?", (symbol,))
            db.set_setting("cash", str(cash + qty * price))
        else:
            notify_slack_order(symbol, action, qty, price, "action must be buy or sell", False)
            return {"ok": False, "status": "failed", "message": "action must be buy or sell"}
        save_trade(symbol, symbol_name(symbol), action, qty, price, reason, True, "filled", "paper order filled")
        notify_slack_order(symbol, action, qty, price, reason or "paper order filled", True)
        return {"ok": True, "status": "filled", "msg1": "paper order filled"}
    else:
        real_orders_enabled = (not config.dry_run) and config.trading_env == "real" and config.enable_live_trading
        order_submission_enabled = (not config.dry_run) and (config.trading_env == "demo" or real_orders_enabled)
        if not order_submission_enabled:
            save_trade(symbol, symbol_name(symbol), action, qty, price, reason, True, "dry_run", "dry run order skipped")
            notify_slack_order(symbol, action, qty, price, reason or "dry run order skipped", True)
            return {"ok": True, "status": "dry_run", "msg1": "dry run order skipped"}
        try:
            client = _get_kis_client()
            res = client.place_overseas_order(symbol, action, price, qty)
            rt_cd = res.get("rt_cd")
            msg = res.get("msg1") or "KIS order response received"
            ok = (rt_cd == "0")
            status = "filled" if ok else "failed"
            save_trade(symbol, symbol_name(symbol), action, qty, price, reason, ok, status, msg)
            notify_slack_order(symbol, action, qty, price, reason or msg, ok)
            return {"ok": ok, "status": status, "msg1": msg, "res": res}
        except Exception as e:
            from src.utils.logger import logger
            logger.error(f"Failed to place KIS US order: {e}")
            save_trade(symbol, symbol_name(symbol), action, qty, price, reason, False, "failed", str(e))
            notify_slack_order(symbol, action, qty, price, str(e), False)
            return {"ok": False, "status": "failed", "message": str(e)}


def cancel_order(symbol: str, order_no: str, qty: float = 0) -> dict[str, Any]:
    symbol = normalize_symbol(symbol)
    if config.trading_env not in {"demo", "real"}:
        return {"ok": False, "status": "unsupported", "message": "broker cancel requires MISTOCK_TRADING_ENV=demo or real"}
    if config.dry_run:
        return {"ok": True, "status": "dry_run", "msg1": "dry run cancel skipped"}
    try:
        res = _get_kis_client().cancel_overseas_order(symbol, order_no, qty=qty)
        return {"ok": res.get("rt_cd") == "0", "status": "submitted" if res.get("rt_cd") == "0" else "failed", "res": res}
    except Exception as exc:
        return {"ok": False, "status": "failed", "message": str(exc)}


def revise_order(symbol: str, order_no: str, qty: float, price: float) -> dict[str, Any]:
    symbol = normalize_symbol(symbol)
    if config.trading_env not in {"demo", "real"}:
        return {"ok": False, "status": "unsupported", "message": "broker revise requires MISTOCK_TRADING_ENV=demo or real"}
    if config.dry_run:
        return {"ok": True, "status": "dry_run", "msg1": "dry run revise skipped"}
    try:
        res = _get_kis_client().revise_overseas_order(symbol, order_no, qty=qty, price=price)
        return {"ok": res.get("rt_cd") == "0", "status": "submitted" if res.get("rt_cd") == "0" else "failed", "res": res}
    except Exception as exc:
        return {"ok": False, "status": "failed", "message": str(exc)}


def save_trade(symbol: str, name: str, action: str, qty: float, price: float, reason: str, ok: bool, order_status: str, response_msg: str) -> None:
    # 수수료/세금 예상 계산 (미장 기본 수수료 0.1%, 매도시 SEC Fee 등 0.03% 추가)
    fee = (qty * price * 0.001) if ok else 0.0
    tax = (qty * price * 0.0003) if (ok and action.lower() == "sell") else 0.0
    exchange_rate = 1380.0
    
    db.execute(
        """
        INSERT INTO trades (ts, symbol, name, action, qty, price, reason, ok, env, dry_run, order_status, response_msg, broker_result, fee, tax, exchange_rate)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            db.now_text(), symbol, name, action, qty, price, reason, int(ok), config.trading_env,
            int(config.dry_run), order_status, response_msg, json.dumps({"paper": True}, ensure_ascii=False),
            fee, tax, exchange_rate,
        ),
    )
