"""
Binance Futures Testnet Auto Trading
"""
from binance.client import Client
import time

print("=== Binance Futures Testnet ===")
print("1. Go to: https://testnet.binancefuture.com")
print("2. Register & Login")
print("3. Go to API (마이페이지) → Create API Key")
print("4. Copy API Key and Secret Key")
print("")
print("Below is the code - you need to enter your API keys")
print("="*40)

API_KEY = "YOUR_API_KEY_HERE"
API_SECRET = "YOUR_SECRET_KEY_HERE"

SYMBOL = "BTCUSDT"
QTY = 0.001

try:
    client = Client(API_KEY, API_SECRET, testnet=True)
    print("[OK] Connected to Binance Testnet")
    
    price = float(client.futures_symbol_ticker(symbol=SYMBOL)['price'])
    print(f"Current Price: ${price:,.2f}")
    
    print("\n[1] Placing BUY order...")
    order = client.futures_create_order(
        symbol=SYMBOL,
        side="BUY",
        type="MARKET",
        quantity=QTY
    )
    print(f"Order ID: {order['orderId']}")
    
    time.sleep(2)
    
    print("\n[2] Checking position...")
    positions = client.futures_position_information(symbol=SYMBOL)
    for pos in positions:
        if float(pos['positionAmt']) != 0:
            print(f"Position: {pos['positionSide']} {pos['positionAmt']}")
            print(f"Entry: ${pos['entryPrice']}")
            print(f"PnL: ${pos['unrealizedProfit']}")
    
    print("\n[3] Closing position...")
    client.futures_create_order(
        symbol=SYMBOL,
        side="SELL",
        type="MARKET",
        quantity=QTY
    )
    print("Position closed!")
    
    print("\n=== Test Complete ===")
    
except Exception as e:
    print(f"[ERROR] {e}")
    print("\nPlease create API key from: https://testnet.binancefuture.com")