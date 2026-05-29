import unittest
import os
import sqlite3
from src.db.repository import load_watchlist_data, save_watchlist_data, init_db, connect_db

class TestWatchlistSettings(unittest.TestCase):
    def setUp(self):
        # 테스트용 임시 DB 설정
        init_db()
        with connect_db() as conn:
            conn.execute("DELETE FROM watchlist_settings WHERE key IN ('ai_auto_add', 'ai_auto_add_threshold')")
            conn.commit()

    def test_watchlist_threshold_defaults_and_updates(self):
        # 1. 초기 로드 시 기본 임계값 3.0 검증
        data = load_watchlist_data()
        self.assertIn("ai_auto_add_threshold", data)
        self.assertEqual(data["ai_auto_add_threshold"], 3.0)

        # 2. 임계값 변경 후 저장 및 검증
        data["ai_auto_add_threshold"] = 4.5
        data["ai_auto_add"] = True
        save_watchlist_data(data)

        updated_data = load_watchlist_data()
        self.assertEqual(updated_data["ai_auto_add_threshold"], 4.5)
        self.assertEqual(updated_data["ai_auto_add"], True)

        # 3. 임계값을 다시 2.5로 낮추기
        updated_data["ai_auto_add_threshold"] = 2.5
        save_watchlist_data(updated_data)

        final_data = load_watchlist_data()
        self.assertEqual(final_data["ai_auto_add_threshold"], 2.5)

if __name__ == "__main__":
    unittest.main()
