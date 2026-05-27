import unittest
import sqlite3
from datetime import datetime, timedelta
from unittest.mock import patch

from src.db.repository import (
    connect_db,
    init_db,
    save_scanned_candidate,
    get_scanned_candidates_history,
    delete_scanned_candidate,
    KST
)

class ScannedCandidatesPersistenceTests(unittest.TestCase):
    def setUp(self):
        # Use an in-memory SQLite database for testing isolation
        self.patch_db = patch("src.db.repository.connect_db")
        self.mock_connect = self.patch_db.start()
        
        self.conn = sqlite3.connect(":memory:")
        self.conn.execute("PRAGMA journal_mode=MEMORY")
        
        # Wrap self.conn inside DBWrapper-like behavior
        from src.db.repository import DBWrapper
        self.mock_connect.return_value = DBWrapper(self.conn, is_pg=False)
        
        # Initialize database tables
        init_db()

    def tearDown(self):
        self.conn.close()
        self.patch_db.stop()

    def test_init_db_creates_scanned_candidates_table(self):
        cursor = self.conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='scanned_candidates'")
        row = cursor.fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row[0], "scanned_candidates")

    def test_save_and_retrieve_scanned_candidate(self):
        # Save a sample candidate
        save_scanned_candidate(
            symbol="005930",
            name="삼성전자",
            score=3,
            reasons=["rsi_oversold", "sma_support"],
            price=72000,
            env="demo",
            indicators={"rsi": 28.5, "rsi2": 29.1, "macd_hist": -1.2, "sma20": 71500, "sma60": 73000}
        )

        history = get_scanned_candidates_history(limit=10, days=1)
        self.assertEqual(len(history), 1)
        
        cand = history[0]
        self.assertEqual(cand["symbol"], "005930")
        self.assertEqual(cand["name"], "삼성전자")
        self.assertEqual(cand["score"], 3)
        self.assertEqual(cand["reasons"], "rsi_oversold,sma_support")
        self.assertEqual(cand["price"], 72000)
        self.assertEqual(cand["env"], "demo")
        self.assertEqual(cand["rsi"], 28.5)
        self.assertEqual(cand["rsi2"], 29.1)
        self.assertEqual(cand["macd_hist"], -1.2)
        self.assertEqual(cand["sma20"], 71500)
        self.assertEqual(cand["sma60"], 73000)

    def test_delete_scanned_candidate(self):
        # Save sample candidate
        save_scanned_candidate(
            symbol="000660",
            name="SK하이닉스",
            score=2,
            reasons="macd_golden_cross",
            price=120000,
            env="demo"
        )
        
        history = get_scanned_candidates_history()
        self.assertEqual(len(history), 1)
        cand_id = history[0]["id"]
        
        # Delete candidate
        deleted_count = delete_scanned_candidate(cand_id)
        self.assertEqual(deleted_count, 1)
        
        # Confirm deleted
        history_after = get_scanned_candidates_history()
        self.assertEqual(len(history_after), 0)


if __name__ == "__main__":
    unittest.main()
