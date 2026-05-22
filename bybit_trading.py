from pybit.unified_trading import HTTP
import os
import time

API_KEY = os.getenv("BYBIT_API_KEY", "")
API_SECRET = os.getenv("BYBIT_API_SECRET", "")
BYBIT_TESTNET = os.getenv("BYBIT_TESTNET", "true").lower() == "true"

session = HTTP(testnet=BYBIT_TESTNET, api_key=API_KEY, api_secret=API_SECRET)

SYMBOL = "BTCUSDT"
QTY = "0.001"

def get_price():
    ticker = session.get_tickers(category="linear", symbol=SYMBOL)
    return float(ticker['result']['list'][0]['lastPrice'])

def place_order(side, order_type="Market", price=None):
    if order_type == "Market":
        return session.place_order(
            category="linear",
            symbol=SYMBOL,
            side=side,
            orderType="Market",
            qty=QTY
        )
    else:
        return session.place_order(
            category="linear",
            symbol=SYMBOL,
            side=side,
            orderType="Limit",
            qty=QTY,
            price=price
        )

def get_position():
    result = session.get_positions(category="linear", symbol=SYMBOL)
    positions = result['result']['list']
    if positions and float(positions[0]['size']) > 0:
        return positions[0]
    return None

def get_pnl():
    pos = get_position()
    if pos:
        return float(pos['unrealizedPnl'])
    return 0

print("=== Bybit Trading Bot ===")
print(f"Symbol: {SYMBOL}")
print(f"Qty: {QTY}")
print(f"Current Price: ${get_price():,.2f}")
print()

while True:
    print("--- Menu ---")
    print("1. Buy (Long)")
    print("2. Sell (Short)")
    print("3. Close Position")
    print("4. Check Position & PnL")
    print("5. Exit")
    choice = input("Select: ").strip()

    if choice == "1":
        print(f"Buying {QTY} {SYMBOL}...")
        result = place_order("Buy")
        print(f"Order ID: {result['result']['orderId']}")
    elif choice == "2":
        print(f"Selling {QTY} {SYMBOL}...")
        result = place_order("Sell")
        print(f"Order ID: {result['result']['orderId']}")
    elif choice == "3":
        print("Closing position...")
        pos = get_position()
        if pos:
            side = "Sell" if pos['side'] == "Buy" else "Buy"
            result = place_order(side)
            print(f"Closed! Order ID: {result['result']['orderId']}")
        else:
            print("No position to close")
    elif choice == "4":
        pos = get_position()
        if pos:
            print(f"Position: {pos['side']} {pos['size']}")
            print(f"Entry Price: ${pos['avgPrice']}")
            print(f"Current PnL: ${float(pos['unrealizedPnl']):.2f}")
        else:
            print("No open position")
    elif choice == "5":
        break
    print()