from mock_trading_realtime import MockTradingSimulator, PriceFetcher

sim = MockTradingSimulator()
sim.clear_all()

pf = PriceFetcher()

print("=== Mock Trading with Real-Time Prices ===")
print()

print("[1] Current BTC Price:")
btc_price = pf.get_price("BTC")
print(f"  BTC: ${btc_price:,.2f}")

print("\n[2] Open LONG position")
result = sim.open_position({
    "direction": "long",
    "symbol": "BTC",
    "qty": 0.001
})
print(f"  Opened at: ${result['position']['entry_price']:,.2f}")

print("\n[3] Check status (real-time PnL)")
status = sim.get_status()
pos = status['positions'][0]
print(f"  Current Price: ${pos.get('current_price', 'N/A')}")
print(f"  Current PnL: ${pos.get('current_pnl', 0):.4f}")

print("\n[4] Wait 3 seconds...")
import time
time.sleep(3)

print("\n[5] Check again")
status = sim.get_status()
pos = status['positions'][0]
print(f"  Current Price: ${pos.get('current_price', 'N/A')}")
print(f"  Current PnL: ${pos.get('current_pnl', 0):.4f}")

print("\n[6] Close position")
result = sim.close_position(1)
print(f"  Closed! PnL: ${result['pnl']:.4f}")

print("\n[7] Final Status")
status = sim.get_status()
print(f"  Total PnL: ${status['total_pnl']:.4f}")
print(f"  Win Rate: {status['win_rate']}%")
print(f"  Trades: {status['wins']}W / {status['losses']}L")

print("\n=== Test Complete ===")