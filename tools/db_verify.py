import sqlite3
import time
import sys

db_path = '/home/turtler800/hanstock/.runtime/trades.sqlite'
try:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    print("=== APPROVALS ===")
    rows = conn.execute('SELECT id, created_at, symbol, name, action, qty, price, status, response_msg FROM approvals ORDER BY id DESC LIMIT 20').fetchall()
    for r in rows:
        print(dict(r))
    if not rows:
        print("No approval records found.")

    print("\n=== TRADES ===")
    trades = conn.execute('SELECT id, ts, symbol, name, action, qty, price, ok, order_status, response_msg FROM trades ORDER BY id DESC LIMIT 20').fetchall()
    for r in trades:
        print(dict(r))
    if not trades:
        print("No trade records found.")
except Exception as e:
    print(f"Error querying database: {e}")

print("\n=== MEASURING CANDIDATES RUNTIME ===")
t0 = time.time()
try:
    sys.path.insert(0, '/home/turtler800/hanstock')
    from src.strategy.seven_split import find_candidates
    print("Starting candidate scan...")
    res = find_candidates(set(), min_score=2)
    print(f"Scanned {len(res['candidates'])} candidates in {time.time() - t0:.2f} seconds")
except Exception as e:
    print(f"Candidate scan failed: {e}")
