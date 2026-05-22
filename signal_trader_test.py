from signal_trader import SignalTrader
from mock_trading_realtime import PriceFetcher

trader = SignalTrader()

print("=== Integration Test ===\n")

print("[1] Fetch signals from API...")
signals = trader.fetch_signals()
print(f"  Found {len(signals)} signals")

if signals:
    print("\n[2] Latest signal:")
    s = signals[0]
    print(f"  Time: {s.get('received_at')}")
    print(f"  Symbol: {s.get('symbol')}")
    print(f"  Direction: {s.get('direction')}")
    print(f"  Entry: {s.get('entry_price')}")
    print(f"  Channel: {s.get('channel')}")

print("\n[3] Check current price...")
pf = PriceFetcher()
btc = pf.get_price("BTC")
print(f"  BTC: ${btc:,.2f}")

print("\n[4] Current trading status...")
status = trader.sim.get_status()
print(f"  Open: {status['open_positions']}")
print(f"  Closed: {status['closed_trades']}")
print(f"  Total PnL: ${status['total_pnl']:.4f}")

print("\n=== Ready to run ===")
print("Run: python signal_trader.py")
print("This will:")
print("  1. Poll Telegram signals every 10 seconds")
print("  2. Auto-open virtual positions for new signals")
print("  3. Track real-time PnL with live Binance prices")
print("  4. Auto-close on exit signals")