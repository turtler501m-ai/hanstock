# -*- coding: utf-8 -*-
from fastapi import Body, HTTPException, Request
from fastapi.responses import FileResponse
import src.dashboard.core as _core
from src.dashboard.core import *
globals().update({k: v for k, v in _core.__dict__.items() if not k.startswith('__')})

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




@app.get("/api/watchlist")
def get_watchlist():
    from src.db.repository import load_watchlist_data, get_watchlist_extra_info
    from src.strategy.seven_split import STOCK_NAMES, STOCK_SECTORS
    data = load_watchlist_data()
    symbols_detail = []
    for code in data.get("symbols", []):
        extra = get_watchlist_extra_info(code)
        symbols_detail.append({
            "symbol": code,
            "name": STOCK_NAMES.get(code, "알 수 없는 종목"),
            "sector": STOCK_SECTORS.get(code, "미분류"),
            "price": extra["price"],
            "score": extra["score"],
            "reason": extra["reason"],
            "change_rate": extra["change_rate"],
            "rsi": extra["rsi"],
            "updated_at": extra["updated_at"]
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




@app.post("/api/trades/order-status/sync")
def sync_trade_order_status(days: int = 7):
    if trader.DRY_RUN:
        raise HTTPException(status_code=400, detail="Order status sync requires DRY_RUN=false")
    try:
        return _sync_order_status_from_history(_get_api(), days=days)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e




@app.post("/api/trades/sync")
def sync_trades(days: int = 90):
    if trader.DRY_RUN:
        raise HTTPException(status_code=400, detail="紐⑥쓽 ?ㅽ뻾(DRY_RUN) 紐⑤뱶?먯꽌??利앷텒??怨꾩쥖 ?숆린?붾? ?ъ슜?????놁뒿?덈떎.")
    try:
        api = _get_api()
        history_sync = None
        history_error = None
        try:
            history_sync = _sync_filled_trades_from_history(api, days=days)
        except Exception as exc:
            history_error = str(exc)

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
                
        imported_count = _to_int(history_sync.get("imported_count")) if history_sync else 0
        updated_count = _to_int(history_sync.get("updated_count")) if history_sync else 0
        return {
            "ok": True,
            "synced_count": synced_count + imported_count,
            "balance_synced_count": synced_count,
            "history_imported_count": imported_count,
            "history_updated_count": updated_count,
            "history_sync": history_sync,
            "history_error": history_error,
        }
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




@app.get("/api/scheduler/status")
def get_scheduler_status():
    global _scheduler_run_state
    
    config = {
        "cron_tz": os.environ.get("HANSTOCK_CRON_TZ", "Asia/Seoul"),
        "daily_auto_retries": os.environ.get("HANSTOCK_DAILY_AUTO_RETRIES", "3"),
        "daily_auto_retry_delay_seconds": os.environ.get("HANSTOCK_DAILY_AUTO_RETRY_DELAY_SECONDS", "10"),
        "scheduler_retries": os.environ.get("HANSTOCK_SCHEDULER_RETRIES", "1"),
        "scheduler_retry_delay_seconds": os.environ.get("HANSTOCK_SCHEDULER_RETRY_DELAY_SECONDS", "5"),
        "slack_enabled": os.environ.get("HANSTOCK_SCHEDULER_SLACK", "true"),
        "sync_enabled": os.environ.get("HANSTOCK_ORDER_STATUS_SYNC", "true"),
        "result_path": os.environ.get("HANSTOCK_SCHEDULER_RESULT_PATH", ".runtime/daily_auto_last_result.json"),
        "trading_env": trader.TRADING_ENV,
        "dry_run": trader.DRY_RUN,
        "order_submission": trader.ORDER_SUBMISSION_ENABLED,
    }
    
    last_result = None
    try:
        from src.db.repository import load_today_scheduler_results, load_latest_scheduler_result
        last_result = load_today_scheduler_results()
        if last_result is None:
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
