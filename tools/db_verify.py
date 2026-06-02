import sqlite3

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
