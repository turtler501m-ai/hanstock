# -*- coding: utf-8 -*-
"""AI stock 자동 매매 활성화 도구.

DB의 automation_policies 테이블을 Level 6(EXECUTE, auto_approve=1, auto_execute=1)으로 강제 업데이트하고,
.env 파일의 승인 필요 플래그를 자동으로 전송되도록 현행화한다.
"""
import os
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / ".runtime" / "trades.sqlite"
ENV_PATH = ROOT / ".env"

def update_db() -> None:
    if not DB_PATH.exists():
        print(f"[db] DB file not found: {DB_PATH}. Creating directory and initializing table if needed.")
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    
    # 테이블 존재 여부 확인 및 생성
    cur.execute("""
        CREATE TABLE IF NOT EXISTS ai_stock_automation_policies (
            strategy_id TEXT,
            market TEXT,
            enabled INTEGER DEFAULT 1,
            automation_level INTEGER DEFAULT 4,
            auto_approve INTEGER DEFAULT 0,
            auto_execute INTEGER DEFAULT 0,
            allow_fallback_trade INTEGER DEFAULT 1,
            allow_stale_data_trade INTEGER DEFAULT 0,
            min_final_score REAL DEFAULT 65.0,
            min_rule_score REAL DEFAULT 40.0,
            max_risk_score REAL DEFAULT 60.0,
            max_daily_orders INTEGER DEFAULT 5,
            max_position_pct REAL DEFAULT 10.0,
            max_market_exposure_pct REAL DEFAULT 50.0,
            max_risk_per_trade_pct REAL DEFAULT 1.0,
            min_price REAL DEFAULT 0.0,
            min_market_cap REAL DEFAULT 0.0,
            min_avg_trading_value REAL DEFAULT 0.0,
            PRIMARY KEY (strategy_id, market)
        )
    """)
    
    # 기본 타겟 정책들 강제 입력 또는 레벨 6으로 업데이트
    targets = [
        ("ai_stock_default_v1", "KR"),
        ("ai_stock_default_v1", "US"),
        ("seven_split", "KR"),
        ("seven_split", "US"),
    ]
    
    for strategy_id, market in targets:
        cur.execute("""
            INSERT INTO ai_stock_automation_policies (
                strategy_id, market, enabled, automation_level, auto_approve, auto_execute, max_daily_orders
            ) VALUES (?, ?, 1, 6, 1, 1, 10)
            ON CONFLICT(strategy_id, market) DO UPDATE SET
                enabled = 1,
                automation_level = 6,
                auto_approve = 1,
                auto_execute = 1,
                max_daily_orders = 10
        """, (strategy_id, market))
    
    conn.commit()
    
    # 현재 상태 출력
    cur.execute("SELECT strategy_id, market, automation_level, auto_approve, auto_execute FROM ai_stock_automation_policies")
    print("== Updated DB Automation Policies ==")
    for row in cur.fetchall():
        print(f"Strategy: {row[0]} | Market: {row[1]} | Level: {row[2]} | AutoApprove: {row[3]} | AutoExecute: {row[4]}")
    conn.close()

def update_env() -> None:
    if not ENV_PATH.exists():
        print(f"[env] .env file not found: {ENV_PATH}")
        return

    content = ENV_PATH.read_text(encoding="utf-8")
    lines = content.splitlines()
    new_lines = []
    
    updates = {
        "REQUIRE_APPROVAL": "false",
        "AI_AUTO_APPROVE": "true",
        "AI_STRATEGY_ENABLED": "True"
    }
    
    seen = set()
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            new_lines.append(line)
            continue
        
        if "=" in line:
            key, val = stripped.split("=", 1)
            key = key.strip()
            if key in updates:
                new_lines.append(f"{key}={updates[key]}")
                seen.add(key)
                print(f"[env] updated: {key} -> {updates[key]}")
                continue
        new_lines.append(line)
        
    # 누락된 설정 추가
    for key, val in updates.items():
        if key not in seen:
            new_lines.append(f"{key}={val}")
            print(f"[env] appended: {key} -> {val}")
            
    ENV_PATH.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
    print("[env] .env file update completed successfully.")

if __name__ == "__main__":
    update_db()
    update_env()
