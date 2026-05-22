"""
Telegram Signal → Mock Trading Integration
실시간으로 Telegram 신호를 받아와서 모의거래 시뮬레이션
"""
import json
import os
import time
import requests
from datetime import datetime
from pathlib import Path

# Mock Trading & Price Fetcher import
from mock_trading_realtime import MockTradingSimulator, PriceFetcher


class SignalTrader:
    def __init__(self):
        self.sim = MockTradingSimulator()
        self.pf = PriceFetcher()
        self.state_file = Path(".runtime/signal_trader_state.json")
        self.state = self._load_state()
        self.api_url = "http://localhost:8000"

    def _load_state(self):
        if self.state_file.exists():
            try:
                return json.loads(self.state_file.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {"processed_signal_ids": []}

    def _save_state(self):
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        self.state_file.write_text(json.dumps(self.state, ensure_ascii=False, indent=2), encoding="utf-8")

    def _mark_processed(self, signal_id: str):
        processed = self.state.setdefault("processed_signal_ids", [])
        if signal_id not in processed:
            processed.append(signal_id)
        self.state["processed_signal_ids"] = processed[-2000:]
        self._save_state()

    def fetch_signals(self):
        """API에서 신호 가져오기"""
        try:
            resp = requests.get(f"{self.api_url}/api/futures-signals?limit=500", timeout=10)
            resp.raise_for_status()
            data = resp.json()
            return data.get("signals", [])
        except Exception as e:
            print(f"[ERROR] Fetch signals: {e}")
            return []

    def normalize_symbol(self, raw_symbol: str) -> str:
        symbol_upper = str(raw_symbol or "").upper()
        if any(token in symbol_upper for token in ("나스닥", "NASDAQ", "MNQ")):
            return "MNQ"
        if "NQ" in symbol_upper:
            return "NQ"
        if any(token in symbol_upper for token in ("골드", "GOLD", "XAU", "GC")):
            return "GC"
        if any(token in symbol_upper for token in ("크루드", "오일", "OIL", "CRUDE", "WTI", "CL")):
            return "CL"
        if any(token in symbol_upper for token in ("에스앤피", "S&P", "SPX", "ES")):
            return "ES"
        if any(token in symbol_upper for token in ("항셍", "HANGSENG", "HANG SENG", "HSI")):
            return "HSI"
        if "BTC" in symbol_upper:
            return "BTC"
        if "ETH" in symbol_upper:
            return "ETH"
        return symbol_upper or "MNQ"

    def _matching_position_id(self, symbol: str):
        for pos in self.sim.data.get("positions", []):
            if pos.get("symbol") == symbol:
                return pos.get("id")
        return None

    def process_signal(self, signal: dict):
        signal_id = str(signal.get("id") or signal.get("internal_id") or "")
        if not signal_id:
            return
        if signal_id in set(self.state.get("processed_signal_ids", [])):
            return

        direction = str(signal.get("direction") or "").lower()
        symbol = self.normalize_symbol(signal.get("symbol", ""))
        targets = signal.get("targets") or []
        take_profit = signal.get("take_profit_1") or (targets[0] if targets else None)
        entry_price = signal.get("entry_price")

        print(f"\n[PROCESS SIGNAL] {signal_id} {direction.upper()} {symbol}")
        if direction in ["long", "short"]:
            result = self.sim.open_position({
                "signal_id": signal_id,
                "direction": direction,
                "symbol": symbol,
                "entry_price": entry_price,
                "stop_loss": signal.get("stop_loss"),
                "take_profit": take_profit,
                "qty": 0.001,
                "provider": signal.get("channel", "unknown"),
                "signal_time": signal.get("received_at"),
                "raw_text": signal.get("raw_text", "")[:300],
            })
            print(f"  result={result.get('status')} {result.get('message', '')}")
        elif direction == "exit":
            position_id = self._matching_position_id(symbol)
            if position_id:
                result = self.sim.close_position(position_id, reason=f"signal_exit:{signal_id}")
                print(f"  closed position={position_id} pnl=${result.get('pnl', 0):.4f}")
            else:
                print("  no matching open position")
        else:
            print(f"  ignored unsupported direction={direction}")

        self._mark_processed(signal_id)

    def process_new_signals(self):
        """새로운 신호 처리"""
        signals = self.fetch_signals()
        if not signals:
            return
        signals = sorted(signals, key=lambda item: item.get("received_at") or "")
        for signal in signals:
            self.process_signal(signal)
    
    def update_market_prices(self):
        """시세 업데이트 및 PnL 계산"""
        self.sim.update_prices()
        
    def display_status(self):
        """상태 표시"""
        status = self.sim.get_status()
        
        print("\n" + "=" * 60)
        print(f"[SIGNAL TRADER STATUS]")
        print("=" * 60)
        
        # 최신 시세 (거래된 심볼만)
        symbols = ["GC", "CL", "MNQ", "NQ", "ES", "BTC", "ETH"]
        print("  Market Prices:")
        for sym in symbols:
            price = self.pf.get_price(sym)
            print(f"    {sym:4s}: ${price:,.2f}")
        
        # 성과
        print(f"\n  Total PnL: ${status['total_pnl']:.4f}")
        print(f"  Win Rate: {status['win_rate']}% ({status['wins']}W/{status['losses']}L)")
        print(f"  Closed: {status['closed_trades']} | Open: {status['open_positions']}")
        
        # 오픈 포지션
        if status['positions']:
            print(f"\n  OPEN POSITIONS:")
            for p in status['positions']:
                pnl = p.get('current_pnl', 0)
                pnl_str = f"+${pnl:.4f}" if pnl >= 0 else f"-${abs(pnl):.4f}"
                print(f"    [{p['id']}] {p['side']} {p['symbol']} @ ${p['entry_price']:,.2f}")
                print(f"        Current: ${p.get('current_price', 'N/A')} | PnL: {pnl_str}")
        
        print("=" * 60)
    
    def run(self, interval=30):
        """실행"""
        print("=== Telegram Signal → Mock Trading ===")
        print(f"API: {self.api_url}")
        print(f"Update Interval: {interval} seconds")
        print()
        
        print("Press Ctrl+C to stop")
        
        counter = 0
        while True:
            try:
                # 신호 확인
                self.process_new_signals()
                
                # 시세 업데이트
                self.update_market_prices()
                
                # 10초마다 상태 표시
                counter += 1
                if counter % 3 == 0:
                    self.display_status()
                    
                time.sleep(interval)
                
            except KeyboardInterrupt:
                print("\n\nStopping...")
                break
            except Exception as e:
                print(f"[ERROR] {e}")
                time.sleep(interval)


def main():
    trader = SignalTrader()
    if os.environ.get("SIGNAL_TRADER_ONCE") == "1":
        trader.process_new_signals()
        trader.update_market_prices()
        trader.display_status()
        return
    trader.run(interval=10)


if __name__ == "__main__":
    main()
