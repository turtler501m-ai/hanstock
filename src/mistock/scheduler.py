from __future__ import annotations

import argparse
import json
import os
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

from src.mistock import trader as mistock_trader
from src.mistock.config import config as mistock_config
from src.mistock import db as mistock_db
from src.notifier.slack import send_mistock_slack
from src.utils.logger import logger

from src.mistock.strategy import symbol_name

KST = timezone(timedelta(hours=9))

def run_mistock_scheduled_cycle(mode: str = "execute") -> dict:
    """
    [미장 자동매매 스케줄러]
    미국 주식 시장(미장) 유니버스 스캔, 신호 분석 및 주문 집행(Paper 또는 KIS 실거래)을 수행합니다.
    """
    logger.info(f"[MISTOCK SCHEDULER] Starting scheduled cycle. Mode={mode}")
    
    # 1. 시세 조회 및 후보 종목 스캔
    scan = mistock_trader.scan_candidates(min_score=2, limit=mistock_config.scan_universe_size)
    candidates = scan["candidates"]
    logger.info(f"[MISTOCK SCHEDULER] Scanned {scan['scanned']} symbols. Found {len(candidates)} candidates.")
    
    # 2. 잔고 가져오기
    balance = mistock_trader.get_balance()
    cash = balance["cash"]
    
    # Check auto-approval setting from database
    auto_approve = (mistock_db.get_setting("auto_approval", "false") == "true")
    flags = mistock_trader.runtime_flags()
    
    # 3. 매도 신호 처리 및 주문 집행/대기등록
    sigs = mistock_trader.signals()
    sold_items = []
    for sig in sigs:
        if sig["action"] == "sell":
            qty = float(sig["signal_qty"])
            price = float(sig["signal_price"])
            if qty > 0:
                if mode == "execute" and (auto_approve or flags["order_submission_enabled"]):
                    logger.info(f"[MISTOCK SCHEDULER] Sell signal for {sig['symbol']}. Qty={qty}, Price={price}")
                    res = mistock_trader.place_paper_order(sig["symbol"], "sell", qty, price, reason=sig["reason"])
                    sold_items.append({"symbol": sig["symbol"], "qty": qty, "price": price, "result": res})
                else:
                    logger.info(f"[MISTOCK SCHEDULER] Auto-approval and order submission disabled/skipped for sell signal. Queuing {sig['symbol']} as pending approval.")
                    now = mistock_db.now_text()
                    mistock_db.execute(
                        """
                        INSERT INTO approvals (created_at, updated_at, symbol, name, action, qty, price, reason, source, status, response_msg)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', '')
                        """,
                        (now, now, sig["symbol"], symbol_name(sig["symbol"]), "sell", qty, price, sig.get("reason") or "보유 종목 매도 신호", "scheduler"),
                    )
                 
    # 4. 매수 주문 조립 및 집행/대기등록
    orders = mistock_trader.build_orders(candidates, cash)
    bought_items = []
    
    if mode == "execute":
        if auto_approve or flags["order_submission_enabled"]:
            for ord in orders:
                qty = float(ord["quantity"])
                price = float(ord["price"])
                logger.info(f"[MISTOCK SCHEDULER] Placing buy order for {ord['symbol']}. Qty={qty}, Price={price}")
                res = mistock_trader.place_paper_order(ord["symbol"], "buy", qty, price, reason=ord["reason"])
                bought_items.append({"symbol": ord["symbol"], "qty": qty, "price": price, "result": res})
        else:
            logger.info("[MISTOCK SCHEDULER] Order submission and auto-approval are disabled. Queuing buy plans as pending approvals.")
            for ord in orders:
                qty = float(ord["quantity"])
                price = float(ord["price"])
                now = mistock_db.now_text()
                mistock_db.execute(
                    """
                    INSERT INTO approvals (created_at, updated_at, symbol, name, action, qty, price, reason, source, status, response_msg)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', '')
                    """,
                    (now, now, ord["symbol"], symbol_name(ord["symbol"]), "buy", qty, price, ord.get("reason") or "매수 계획", "scheduler"),
                )
            
    order_failures = [
        item
        for item in sold_items + bought_items
        if not (item.get("result") or {}).get("ok", False)
    ]
    result = {
        "status": "success" if not order_failures else "failed",
        "ok": not order_failures,
        "scanned": scan["scanned"],
        "candidates": len(candidates),
        "sold": sold_items,
        "bought": bought_items,
        "plan": orders,
        "errors": [
            {
                "symbol": item.get("symbol"),
                "action": "sell" if item in sold_items else "buy",
                "message": (item.get("result") or {}).get("msg1")
                or (item.get("result") or {}).get("message")
                or "order failed",
            }
            for item in order_failures
        ],
    }
    
    # 결과 파일 저장
    path = Path(".runtime/mistock/daily_auto_last_result.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    recorded_at = datetime.now(KST).isoformat()
    path.write_text(json.dumps({
        "recorded_at": recorded_at,
        "result": result,
    }, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    
    # 누적 기록 파일에도 크로노그래피컬하게 누적 저장 (VM 크론탭 실행 누락 방지)
    today_path = Path(".runtime/mistock/daily_auto_today_results.json")
    today_str = datetime.now(KST).strftime("%Y-%m-%d")
    today_runs = []
    if today_path.exists():
        try:
            data = json.loads(today_path.read_text(encoding="utf-8"))
            if isinstance(data, list):
                today_runs = [r for r in data if r.get("recorded_at", "").startswith(today_str)]
        except Exception:
            pass
            
    today_runs.append({
        "recorded_at": recorded_at,
        "mode": mode,
        "result": result
    })
    try:
        today_path.write_text(json.dumps(today_runs, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    except Exception:
        pass
    
    # 슬랙 알림 발송
    if os.environ.get("MISTOCK_SCHEDULER_SLACK", "true").lower() not in {"0", "false", "no", "off"}:
        status_str = "성공"
        lines = [
            f"*상태*: {status_str}",
            f"*스캔 대상*: {scan['scanned']}개 종목",
            f"*보유종목 매도 집행*: {len(sold_items)}건",
            f"*매수 집행*: {len(bought_items)}건 / 계획 {len(orders)}건",
            f"*현재 현금 잔고*: ${balance['cash']:,.2f}",
            f"*총 평가 금액*: ${balance['total_eval']:,.2f}",
            f"*환경*: {mistock_config.trading_env}, dry_run={mistock_config.dry_run}",
        ]
        send_mistock_slack(
            text=f"[미스톡 VM] 미장 자동매매 {status_str}",
            blocks=[
                {"type": "header", "text": {"type": "plain_text", "text": "미스톡 미국주식 자동매매"}},
                {"type": "section", "text": {"type": "mrkdwn", "text": "\n".join(lines)}},
            ],
            color="#36a64f"
        )
        
    return result

def main() -> int:
    parser = argparse.ArgumentParser(description="Mistock US stock scheduled trading runner")
    parser.add_argument(
        "--mode",
        choices=["execute", "analysis_only"],
        default="execute",
        help="execute orders immediately or queue analysis only",
    )
    args = parser.parse_args()
    try:
        run_mistock_scheduled_cycle(mode=args.mode)
        return 0
    except Exception as e:
        logger.error(f"Mistock scheduler execution failed: {e}")
        return 1

if __name__ == "__main__":
    raise SystemExit(main())
