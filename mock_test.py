from mock_trading import MockTradingSimulator

sim = MockTradingSimulator()
sim.clear_all()

print("=== Mock Trading Test ===")

print("\n[1] Open LONG position at $50,000")
result = sim.open_position({
    "direction": "long",
    "symbol": "BTC",
    "entry_price": 50000,
    "qty": 0.001,
    "provider": "GoldMoon"
})
print(f"Opened: {result['position']['id']}")

print("\n[2] Update price to $51,000 (profit)")
result = sim.update_prices({"BTC": 51000})
print(f"Current PnL: ${sim.data['positions'][0].get('current_pnl', 0):.2f}")

print("\n[3] Close at $52,000")
result = sim.close_position(1, 52000, "manual")
print(f"Closed! PnL: ${result['pnl']:.2f}")

print("\n[4] Status")
status = sim.get_status()
print(f"Total PnL: ${status['total_pnl']:.2f}")
print(f"Win Rate: {status['win_rate']:.1f}%")
print(f"Trades: {status['wins']}W / {status['losses']}L")

print("\n[5] Open SHORT position")
sim.open_position({
    "direction": "short",
    "symbol": "BTC",
    "entry_price": 52000,
    "qty": 0.001,
    "provider": "ChartLeader"
})

print("\n[6] Price drops to $50,000 (profit)")
sim.update_prices({"BTC": 50000})
print(f"Current PnL: ${sim.data['positions'][0].get('current_pnl', 0):.2f}")

status = sim.get_status()
print(f"\n=== Final Status ===")
print(f"Open: {status['open_positions']}")
print(f"Closed: {status['closed_trades']}")
print(f"Total PnL: ${status['total_pnl']:.2f}")

print("\n=== Test Complete ===")