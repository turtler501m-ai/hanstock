"""
Telegram Signal → Bybit Auto Trading System
Telegram 신호를 받아서 Bybit에 자동 주문 후 성과 검증
"""
from pybit.unified_trading import HTTP
import json
import os
from datetime import datetime

API_KEY = os.getenv("BYBIT_API_KEY", "")
API_SECRET = os.getenv("BYBIT_API_SECRET", "")
BYBIT_TESTNET = os.getenv("BYBIT_TESTNET", "true").lower() == "true"

session = HTTP(testnet=BYBIT_TESTNET, api_key=API_KEY, api_secret=API_SECRET)

SYMBOL_MAP = {
    "NQ": "BTCUSDT",
    "ES": "USDTUSDC", 
    "GC": "GOLDUSDT",
    "CL": "WTICOUSDT",
    "나스닥": "BTCUSDT",
    "마이크로나스닥": "BTCUSDT",
    "골드": "GOLDUSDT",
    "크루드오일": "WTICOUSDT",
}

class BybitTrader:
    def __init__(self, symbol="BTCUSDT", qty=0.001):
        self.symbol = symbol
        self.qty = str(qty)
        self.session = session
        
    def get_price(self):
        ticker = self.session.get_tickers(category="linear", symbol=self.symbol)
        return float(ticker['result']['list'][0]['lastPrice'])
    
    def buy(self):
        result = self.session.place_order(
            category="linear",
            symbol=self.symbol,
            side="Buy",
            orderType="Market",
            qty=self.qty
        )
        return result
    
    def sell(self):
        result = self.session.place_order(
            category="linear",
            symbol=self.symbol,
            side="Sell",
            orderType="Market",
            qty=self.qty
        )
        return result
    
    def close_position(self):
        pos = self.get_position()
        if pos and float(pos['size']) > 0:
            side = "Sell" if pos['side'] == "Buy" else "Buy"
            result = self.session.place_order(
                category="linear",
                symbol=self.symbol,
                side=side,
                orderType="Market",
                qty=pos['size']
            )
            return result
        return None
    
    def get_position(self):
        result = self.session.get_positions(category="linear", symbol=self.symbol)
        positions = result['result']['list']
        if positions and float(positions[0]['size']) > 0:
            return positions[0]
        return None
    
    def get_pnl(self):
        pos = self.get_position()
        if pos:
            return {
                "side": pos['side'],
                "size": pos['size'],
                "entry_price": float(pos['avgPrice']),
                "current_price": self.get_price(),
                "unrealized_pnl": float(pos['unrealizedPnl'])
            }
        return None
    
    def process_signal(self, signal):
        """
        Process trading signal from Telegram
        signal: {"direction": "long/short/exit", "symbol": "NQ/GC/CL", ...}
        """
        direction = signal.get("direction", "").lower()
        
        if direction == "exit":
            print("[EXIT] Closing position...")
            result = self.close_position()
            if result:
                return {"status": "closed", "order_id": result['result']['orderId']}
            return {"status": "no_position"}
        
        symbol = signal.get("symbol", "NQ")
        bybit_symbol = SYMBOL_MAP.get(symbol, "BTCUSDT")
        
        if bybit_symbol != self.symbol:
            print(f"[WARN] Symbol mismatch: {symbol} -> {bybit_symbol}")
        
        if direction in ["long", "buy"]:
            print(f"[LONG] Buying {self.symbol}...")
            result = self.buy()
            return {"status": "buy", "order_id": result['result']['orderId']}
        
        elif direction in ["short", "sell"]:
            print(f"[SHORT] Selling {self.symbol}...")
            result = self.sell()
            return {"status": "sell", "order_id": result['result']['orderId']}
        
        return {"status": "unknown_direction"}

def load_pending_signals():
    """Load signals from futures signals system"""
    signals_file = ".runtime/signals.json"
    if os.path.exists(signals_file):
        with open(signals_file, "r", encoding="utf-8") as f:
            return json.load(f)
    return []

def main():
    trader = BybitTrader(symbol="BTCUSDT", qty=0.001)
    
    print("=== Bybit Auto Trading System ===")
    print(f"Symbol: {trader.symbol}")
    print(f"Qty: {trader.qty}")
    print(f"Current Price: ${trader.get_price():,.2f}")
    print()
    
    print("--- Menu ---")
    print("1. Check current price")
    print("2. Buy (Long)")
    print("3. Sell (Short)")
    print("4. Close position")
    print("5. Check PnL")
    print("6. Process signal")
    print("7. Exit")
    
    while True:
        choice = input("\nSelect: ").strip()
        
        if choice == "1":
            print(f"Price: ${trader.get_price():,.2f}")
            
        elif choice == "2":
            result = trader.buy()
            print(f"Buy Order: {result['result']['orderId']}")
            
        elif choice == "3":
            result = trader.sell()
            print(f"Sell Order: {result['result']['orderId']}")
            
        elif choice == "4":
            result = trader.close_position()
            if result:
                print(f"Closed: {result['result']['orderId']}")
            else:
                print("No position")
                
        elif choice == "5":
            pnl = trader.get_pnl()
            if pnl:
                print(f"Position: {pnl['side']} {pnl['size']}")
                print(f"Entry: ${pnl['entry_price']:,.2f}")
                print(f"Current: ${pnl['current_price']:,.2f}")
                print(f"PnL: ${pnl['unrealized_pnl']:.2f}")
            else:
                print("No position")
                
        elif choice == "6":
            print("Enter signal (direction symbol):")
            sig = input("  direction (long/short/exit): ").strip()
            sym = input("  symbol (NQ/GC/CL): ").strip()
            signal = {"direction": sig, "symbol": sym}
            result = trader.process_signal(signal)
            print(f"Result: {result}")
            
        elif choice == "7":
            break

if __name__ == "__main__":
    main()