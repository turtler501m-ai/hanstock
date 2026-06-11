import sqlite3
import os

db_path = "/home/turtler801/hanstock/.runtime/mistock/trades.sqlite"
if not os.path.exists(db_path):
    print("Database not found")
    exit(1)

conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row

# 전체 데이터 조회
rows = conn.execute("SELECT symbol, name, created_at FROM watchlist").fetchall()
print(f"Total current items: {len(rows)}")

# 지울 항목 선별
# AAPL, MSFT, NVDA, AMZN, META, GOOGL, TSLA, AVGO, AMD, NFLX 이외의 종목 중 
# 오늘(2026-06-11) 19:11 경에 생성된 항목들
defaults = {"AAPL", "MSFT", "NVDA", "AMZN", "META", "GOOGL", "TSLA", "AVGO", "AMD", "NFLX"}

delete_count = 0
for r in rows:
    sym = r["symbol"]
    created = r["created_at"]
    # 2026-06-11 19:11경에 생성된 항목이고 defaults에 없는 경우 삭제
    if sym not in defaults and "2026-06-11 19:11" in created:
        print(f"Deleting auto-migrated symbol: {sym} (created at {created})")
        conn.execute("DELETE FROM watchlist WHERE symbol = ?", (sym,))
        delete_count += 1

conn.commit()
print(f"Deleted {delete_count} auto-migrated items.")

# 최종 남은 목록 확인
remains = conn.execute("SELECT symbol, name, created_at FROM watchlist").fetchall()
print(f"Remaining items: {len(remains)}")
for r in remains:
    print(f" - {r['symbol']}: {r['name']} ({r['created_at']})")

conn.close()
