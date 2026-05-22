from signal_trader import SignalTrader
import time

trader = SignalTrader()

print("=== Running Signal Trader (30 seconds test) ===\n")

# 3번 반복 (30초)
for i in range(3):
    print(f"\n--- Cycle {i+1}/3 ---")
    
    # 신호 처리
    trader.process_new_signals()
    
    # 시세 업데이트
    trader.update_market_prices()
    
    # 상태 표시
    trader.display_status()
    
    time.sleep(10)

print("\n=== Test Complete ===")
print("To run continuously: python signal_trader.py")