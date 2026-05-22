"""
Mock Trading Simulator
Telegram 신호를 받아서 가상의 포지션으로 시뮬레이션 후 성과 검증
"""
import json
import os
from datetime import datetime
from typing import Optional

class MockTradingSimulator:
    def __init__(self, data_file=".runtime/mock_trades.json"):
        self.data_file = data_file
        self.data = self._load_data()
        
    def _load_data(self):
        if os.path.exists(self.data_file):
            with open(self.data_file, "r", encoding="utf-8") as f:
                return json.load(f)
        return {"positions": [], "history": [], "balance": 10000}
    
    def _save_data(self):
        os.makedirs(".runtime", exist_ok=True)
        with open(self.data_file, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)
    
    def open_position(self, signal: dict) -> dict:
        """신호를 받아서 가상의 포지션 오픈"""
        direction = signal.get("direction", "").lower()
        symbol = signal.get("symbol", "BTC")
        
        if direction in ["long", "buy"]:
            side = "LONG"
        elif direction in ["short", "sell"]:
            side = "SHORT"
        else:
            return {"status": "error", "message": "Unknown direction"}
        
        position = {
            "id": len(self.data["positions"]) + 1,
            "symbol": symbol,
            "side": side,
            "entry_price": signal.get("entry_price", 0),
            "entry_time": datetime.now().isoformat(),
            "qty": signal.get("qty", 0.001),
            "sl": signal.get("stop_loss"),
            "tp": signal.get("take_profit"),
            "signal_source": signal.get("provider", "unknown"),
            "raw_signal": signal.get("raw_text", "")[:100]
        }
        
        self.data["positions"].append(position)
        self._save_data()
        
        return {"status": "opened", "position": position}
    
    def close_position(self, position_id: int, exit_price: float, reason: str = "manual") -> dict:
        """포지션 종료 (수동 또는 SL/TP 히트)"""
        positions = self.data["positions"]
        
        for i, pos in enumerate(positions):
            if pos["id"] == position_id:
                closed = positions.pop(i)
                closed["exit_price"] = exit_price
                closed["exit_time"] = datetime.now().isoformat()
                closed["exit_reason"] = reason
                
                entry = closed["entry_price"]
                qty = closed["qty"]
                
                if closed["side"] == "LONG":
                    pnl = (exit_price - entry) * qty
                else:
                    pnl = (entry - exit_price) * qty
                
                closed["pnl"] = pnl
                closed["pnl_pct"] = (pnl / (entry * qty)) * 100 if entry > 0 else 0
                
                self.data["history"].append(closed)
                self._save_data()
                
                return {"status": "closed", "pnl": pnl, "position": closed}
        
        return {"status": "error", "message": "Position not found"}
    
    def update_prices(self, prices: dict):
        """시세 업데이트 (각 포지션의 현재 손익 계산)"""
        for pos in self.data["positions"]:
            symbol = pos["symbol"]
            if symbol in prices:
                current_price = prices[symbol]
                entry = pos["entry_price"]
                qty = pos["qty"]
                
                if pos["side"] == "LONG":
                    pnl = (current_price - entry) * qty
                else:
                    pnl = (entry - current_price) * qty
                
                pos["current_price"] = current_price
                pos["current_pnl"] = pnl
                
                # SL/TP 체크
                if pos["sl"] and current_price <= pos["sl"]:
                    if pos["side"] == "LONG":
                        return {"trigger": "SL", "position_id": pos["id"], "price": current_price}
                if pos["tp"] and current_price >= pos["tp"]:
                    if pos["side"] == "LONG":
                        return {"trigger": "TP", "position_id": pos["id"], "price": current_price}
        
        self._save_data()
        return None
    
    def get_status(self) -> dict:
        """현재 포지션 및 성과 요약"""
        positions = self.data["positions"]
        history = self.data["history"]
        
        total_pnl = sum(h.get("pnl", 0) for h in history)
        win_count = sum(1 for h in history if h.get("pnl", 0) > 0)
        loss_count = sum(1 for h in history if h.get("pnl", 0) <= 0)
        
        return {
            "open_positions": len(positions),
            "closed_trades": len(history),
            "total_pnl": total_pnl,
            "win_rate": (win_count / len(history) * 100) if history else 0,
            "wins": win_count,
            "losses": loss_count,
            "positions": positions,
            "recent_history": history[-10:] if history else []
        }
    
    def process_telegram_signal(self, signal: dict) -> dict:
        """Telegram 신호 처리 (진입/청산)"""
        direction = signal.get("direction", "").lower()
        
        # 청산 신호
        if direction == "exit":
            if self.data["positions"]:
                pos = self.data["positions"][0]
                return self.close_position(pos["id"], signal.get("exit_price", 0), "signal_exit")
            return {"status": "no_position"}
        
        # 진입 신호
        return self.open_position(signal)
    
    def clear_all(self):
        """데이터 초기화"""
        self.data = {"positions": [], "history": [], "balance": 10000}
        self._save_data()


# Telegram 신호 파싱하여 시뮬레이터에 전달
def process_signal_from_telegram(telegram_signal: dict, prices: dict) -> dict:
    """
    Telegram에서 받은 신호를 시뮬레이터로 처리
    """
    sim = MockTradingSimulator()
    
    # 신호 정규화
    direction = telegram_signal.get("direction", "")
    symbol = telegram_signal.get("symbol", "BTC")
    
    if direction == "exit":
        return sim.close_position(
            position_id=telegram_signal.get("position_id", 1),
            exit_price=telegram_signal.get("exit_price", prices.get(symbol, 0)),
            reason="signal"
        )
    
    # 진입 신호
    signal = {
        "direction": direction,
        "symbol": symbol,
        "entry_price": telegram_signal.get("entry", prices.get(symbol, 0)),
        "stop_loss": telegram_signal.get("stop_loss"),
        "take_profit": telegram_signal.get("take_profit"),
        "qty": 0.001,
        "provider": telegram_signal.get("channel", "unknown"),
        "raw_text": telegram_signal.get("raw_text", "")
    }
    
    return sim.open_position(signal)


def main():
    sim = MockTradingSimulator()
    
    print("=== Mock Trading Simulator ===")
    print("1. Open Position (진입)")
    print("2. Close Position (청산)")
    print("3. Check Status (상태확인)")
    print("4. Clear All (초기화)")
    print("5. Simulate Signal (신호처리)")
    
    while True:
        cmd = input("\nSelect: ").strip()
        
        if cmd == "1":
            print("\n--- Open Position ---")
            symbol = input("Symbol (BTC/NQ/GC): ").strip()
            side = input("Side (long/short): ").strip()
            price = float(input("Entry Price: ").strip())
            result = sim.open_position({
                "direction": side,
                "symbol": symbol,
                "entry_price": price,
                "qty": 0.001
            })
            print(f"Result: {result}")
            
        elif cmd == "2":
            status = sim.get_status()
            print(f"Open Positions: {status['open_positions']}")
            if status['positions']:
                pos = status['positions'][0]
                pid = int(input(f"Position ID (default {pos['id']}): ").strip() or pos['id'])
                exit_price = float(input("Exit Price: ").strip())
                result = sim.close_position(pid, exit_price)
                print(f"Closed: {result}")
                
        elif cmd == "3":
            status = sim.get_status()
            print(f"\n=== Status ===")
            print(f"Open Positions: {status['open_positions']}")
            print(f"Closed Trades: {status['closed_trades']}")
            print(f"Total PnL: ${status['total_pnl']:.2f}")
            print(f"Win Rate: {status['win_rate']:.1f}%")
            print(f"W/L: {status['wins']}/{status['losses']}")
            if status['positions']:
                print("\nOpen Positions:")
                for p in status['positions']:
                    print(f"  [{p['id']}] {p['side']} {p['symbol']} @ ${p['entry_price']} | PnL: ${p.get('current_pnl', 0):.2f}")
                    
        elif cmd == "4":
            sim.clear_all()
            print("Cleared!")
            
        elif cmd == "5":
            print("\n--- Simulate Signal ---")
            sig = input("Direction (long/short/exit): ").strip()
            sym = input("Symbol (BTC): ").strip()
            price = float(input("Price: ").strip())
            
            result = process_signal_from_telegram(
                {"direction": sig, "symbol": sym, "entry": price},
                {sym: price}
            )
            print(f"Result: {result}")
            
        elif cmd == "q":
            break


if __name__ == "__main__":
    main()