"""
Mock Trading Simulator with Real-Time Prices
Telegram 신호 → 가상의 포지션 → 실제 시세 추적 → 성과 검증
한국투자 KIS API + Binance fallback
"""
import json
import os
import sys
import time
import requests
import yfinance as yf
from datetime import datetime
from typing import Optional, Dict

# Add src to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

class PriceFetcher:
    """실제 시세 조회 - Yahoo Finance 우선, Binance fallback"""
    
    SYMBOL_MAP_YF = {
        "GC": "GC=F",       # Gold futures
        "XAU": "GC=F",
        "CL": "CL=F",       # Crude Oil
        "NQ": "NQ=F",       # Nasdaq futures
        "MNQ": "MNQ=F",     # Mini Nasdaq
        "ES": "ES=F",       # S&P500
        "HSI": "HSI=F",     # Hang Seng futures
        "BTC": "BTC-USD",
        "ETH": "ETH-USD",
    }
    
    SYMBOL_MAP_BINANCE = {
        "BTC": "BTCUSDT",
        "ETH": "ETHUSDT",
    }
    
    def __init__(self):
        pass  # No API initialization needed
    
    def get_price(self, symbol: str) -> float:
        """시세 조회 - Yahoo Finance 우선, Binance fallback"""
        
        # Try Yahoo Finance first
        yf_ticker = self.SYMBOL_MAP_YF.get(symbol)
        if yf_ticker:
            try:
                ticker = yf.Ticker(yf_ticker)
                info = ticker.info
                price = info.get("currentPrice") or info.get("regularMarketPrice")
                if price:
                    print(f"[Yahoo] {symbol} ({yf_ticker}): ${price}")
                    return float(price)
            except Exception as e:
                print(f"[WARN] Yahoo Finance error: {e}")
        
        # Fallback to Binance (Crypto only)
        binance_symbol = self.SYMBOL_MAP_BINANCE.get(symbol, symbol + "USDT")
        if binance_symbol:
            try:
                url = f"https://api.binance.com/api/v3/ticker/price?symbol={binance_symbol}"
                resp = requests.get(url, timeout=5)
                price = float(resp.json()['price'])
                print(f"[Binance] {symbol}: ${price}")
                return price
            except Exception as e:
                print(f"[ERROR] Binance error: {e}")
        
        return 0
    
    @staticmethod
    def get_prices(symbols: list) -> Dict[str, float]:
        """여러 시세 조회"""
        fetcher = PriceFetcher()
        prices = {}
        for sym in symbols:
            prices[sym] = fetcher.get_price(sym)
        return prices


class MockTradingSimulator:
    def __init__(self, data_file=".runtime/mock_trades.json"):
        self.data_file = data_file
        self.data = self._load_data()
        self.price_fetcher = PriceFetcher()
        
    def _load_data(self):
        if os.path.exists(self.data_file):
            with open(self.data_file, "r", encoding="utf-8-sig") as f:
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
        signal_id = signal.get("signal_id") or signal.get("id")

        if signal_id:
            for pos in self.data.get("positions", []):
                if pos.get("source_signal_id") == signal_id:
                    return {"status": "duplicate", "position": pos}
            for trade in self.data.get("history", []):
                if trade.get("source_signal_id") == signal_id:
                    return {"status": "duplicate", "position": trade}
        
        # 실제 시세로 진입가 설정 (지정되지 않은 경우)
        entry_price = signal.get("entry_price")
        if not entry_price or entry_price == 0:
            entry_price = self.price_fetcher.get_price(symbol)
        if not entry_price or entry_price <= 0:
            return {"status": "error", "message": f"Price unavailable for {symbol}"}
        
        if direction in ["long", "buy"]:
            side = "LONG"
        elif direction in ["short", "sell"]:
            side = "SHORT"
        else:
            return {"status": "error", "message": "Unknown direction"}

        existing_ids = [int(pos.get("id", 0) or 0) for pos in self.data.get("positions", [])]
        existing_ids.extend(int(item.get("id", 0) or 0) for item in self.data.get("history", []))
        next_id = max(existing_ids, default=0) + 1
        
        position = {
            "id": next_id,
            "symbol": symbol,
            "side": side,
            "entry_price": entry_price,
            "entry_time": datetime.now().isoformat(),
            "qty": signal.get("qty", 0.001),
            "sl": signal.get("stop_loss"),
            "tp": signal.get("take_profit"),
            "signal_source": signal.get("provider", "unknown"),
            "source_signal_id": signal_id,
            "signal_time": signal.get("signal_time"),
            "raw_signal": signal.get("raw_text", "")[:100]
        }
        
        self.data["positions"].append(position)
        self._save_data()
        
        return {"status": "opened", "position": position}
    
    def close_position(self, position_id: int, exit_price: float = None, reason: str = "manual") -> dict:
        """포지션 종료"""
        positions = self.data["positions"]
        
        for i, pos in enumerate(positions):
            if pos["id"] == position_id:
                closed = positions.pop(i)
                
                # 시세 미지정시 현재가 사용
                if not exit_price or exit_price == 0:
                    exit_price = self.price_fetcher.get_price(pos["symbol"])
                
                closed["exit_price"] = exit_price
                closed["exit_time"] = datetime.now().isoformat()
                closed["exit_reason"] = reason
                
                entry = closed["entry_price"]
                qty = closed["qty"]
                
                if closed["side"] == "LONG":
                    pnl = (exit_price - entry) * qty
                else:
                    pnl = (entry - exit_price) * qty
                
                closed["pnl"] = round(pnl, 4)
                closed["pnl_pct"] = round((pnl / (entry * qty)) * 100, 2) if entry > 0 else 0
                
                self.data["history"].append(closed)
                self._save_data()
                
                return {"status": "closed", "pnl": round(pnl, 4), "position": closed}
        
        return {"status": "error", "message": "Position not found"}
    
    def update_prices(self):
        """실제 시세로 업데이트"""
        # 모든 포지션의 시세 업데이트
        for pos in self.data["positions"]:
            symbol = pos["symbol"]
            current_price = self.price_fetcher.get_price(symbol)
            
            if current_price > 0:
                entry = pos["entry_price"]
                qty = pos["qty"]
                
                if pos["side"] == "LONG":
                    pnl = (current_price - entry) * qty
                else:
                    pnl = (entry - current_price) * qty
                
                pos["current_price"] = current_price
                pos["current_pnl"] = round(pnl, 4)
                
                sl = pos.get("sl")
                tp = pos.get("tp")
                if pos["side"] == "LONG":
                    if sl and current_price <= sl:
                        self.close_position(pos["id"], current_price, "SL")
                        return {"trigger": "SL", "position_id": pos["id"], "price": current_price}
                    if tp and current_price >= tp:
                        self.close_position(pos["id"], current_price, "TP")
                        return {"trigger": "TP", "position_id": pos["id"], "price": current_price}
                else:
                    if sl and current_price >= sl:
                        self.close_position(pos["id"], current_price, "SL")
                        return {"trigger": "SL", "position_id": pos["id"], "price": current_price}
                    if tp and current_price <= tp:
                        self.close_position(pos["id"], current_price, "TP")
                        return {"trigger": "TP", "position_id": pos["id"], "price": current_price}
        
        self._save_data()
        return None
    
    def get_status(self) -> dict:
        """현재 포지션 및 성과 요약"""
        # 시세 업데이트
        self.update_prices()
        
        positions = self.data["positions"]
        history = self.data["history"]
        
        total_pnl = sum(h.get("pnl", 0) for h in history)
        win_count = sum(1 for h in history if h.get("pnl", 0) > 0)
        loss_count = sum(1 for h in history if h.get("pnl", 0) <= 0)
        
        return {
            "open_positions": len(positions),
            "closed_trades": len(history),
            "total_pnl": round(total_pnl, 4),
            "win_rate": round((win_count / len(history) * 100), 1) if history else 0,
            "wins": win_count,
            "losses": loss_count,
            "positions": positions,
            "recent_history": history[-10:] if history else []
        }
    
    def process_telegram_signal(self, signal: dict) -> dict:
        """Telegram 신호 처리"""
        direction = signal.get("direction", "").lower()
        
        if direction == "exit":
            if self.data["positions"]:
                pos = self.data["positions"][0]
                exit_price = signal.get("exit_price", 0)
                return self.close_position(pos["id"], exit_price, "signal_exit")
            return {"status": "no_position"}
        
        return self.open_position(signal)
    
    def clear_all(self):
        """데이터 초기화"""
        self.data = {"positions": [], "history": [], "balance": 10000}
        self._save_data()


def main():
    sim = MockTradingSimulator()
    
    print("=" * 50)
    print("=== Mock Trading with Real-Time Prices ===")
    print("=" * 50)
    print("Data source: Binance Public API")
    print()
    
    while True:
        status = sim.get_status()
        
        print("\n" + "=" * 40)
        print(f"📊 Status: {status['open_positions']} open, {status['closed_trades']} closed")
        print(f"💰 Total PnL: ${status['total_pnl']:.4f}")
        print(f"📈 Win Rate: {status['win_rate']}% ({status['wins']}W/{status['losses']}L)")
        print("=" * 40)
        
        if status['positions']:
            print("\n📌 Open Positions:")
            for p in status['positions']:
                print(f"  [{p['id']}] {p['side']} {p['symbol']}")
                print(f"      Entry: ${p['entry_price']:,.2f}")
                print(f"      Current: ${p.get('current_price', 'N/A')}")
                print(f"      PnL: ${p.get('current_pnl', 0):.4f}")
                if p.get('sl'): print(f"      SL: ${p['sl']}")
                if p.get('tp'): print(f"      TP: ${p['tp']}")
        
        print("\n--- Menu ---")
        print("1. Open LONG (매수)")
        print("2. Open SHORT (매도)")
        print("3. Close Position (청산)")
        print("4. Check Prices (시세확인)")
        print("5. Process Signal (신호처리)")
        print("6. Clear All (초기화)")
        print("0. Exit")
        
        cmd = input("\nSelect: ").strip()
        
        if cmd == "1":
            print("\n--- Open LONG ---")
            symbol = input("Symbol (BTC/ETH): ").strip().upper()
            qty = float(input("Qty (default 0.001): ").strip() or "0.001")
            result = sim.open_position({
                "direction": "long",
                "symbol": symbol,
                "qty": qty,
                "provider": "manual"
            })
            print(f"[OK] Opened at ${result['position']['entry_price']:,.2f}")
            
        elif cmd == "2":
            print("\n--- Open SHORT ---")
            symbol = input("Symbol (BTC/ETH): ").strip().upper()
            qty = float(input("Qty (default 0.001): ").strip() or "0.001")
            result = sim.open_position({
                "direction": "short",
                "symbol": symbol,
                "qty": qty,
                "provider": "manual"
            })
            print(f"[OK] Opened at ${result['position']['entry_price']:,.2f}")
            
        elif cmd == "3":
            if status['positions']:
                pos = status['positions'][0]
                pid = int(input(f"Position ID (default {pos['id']}): ").strip() or pos['id'])
                result = sim.close_position(pid)
                print(f"[OK] Closed! PnL: ${result.get('pnl', 0):.4f}")
            else:
                print("No open positions")
                
        elif cmd == "4":
            print("\n--- Current Prices ---")
            for sym in ["BTC", "ETH", "BNB"]:
                price = PriceFetcher.get_price(sym)
                print(f"  {sym}: ${price:,.2f}")
                
        elif cmd == "5":
            print("\n--- Process Signal ---")
            sig = input("Direction (long/short/exit): ").strip()
            sym = input("Symbol (BTC): ").strip().upper()
            result = sim.process_telegram_signal({
                "direction": sig,
                "symbol": sym
            })
            print(f"Result: {result}")
            
        elif cmd == "6":
            sim.clear_all()
            print("[OK] Cleared!")
            
        elif cmd == "0":
            break
        
        time.sleep(0.5)


if __name__ == "__main__":
    main()
