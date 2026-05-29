import unittest
from pathlib import Path
import json

from src.db.repository import (
    init_db,
    connect_db,
    load_ai_strategies,
    save_ai_strategies,
    _load_token_usage,
    update_token_usage,
    save_scheduler_result,
    load_latest_scheduler_result,
    load_auto_approval_state,
    save_auto_approval_state
)

class DbMigrationTests(unittest.TestCase):
    def setUp(self):
        init_db()

    def test_ai_strategies_db_persistence(self):
        # Create a test strategy
        test_strat = [
            {
                "id": "test_strat_db",
                "name": "Test Strategy",
                "provider": "openai",
                "model": "gpt-5-mini",
                "weight": 0.5,
                "description": "Test description",
                "selected": True
            }
        ]
        
        # Save to DB
        save_ai_strategies(test_strat)
        
        # Load from DB
        loaded = load_ai_strategies()
        
        # Find our test strategy
        found = [s for s in loaded if s["id"] == "test_strat_db"]
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["name"], "Test Strategy")
        self.assertEqual(found[0]["weight"], 0.5)
        self.assertTrue(found[0]["selected"])

    def test_token_usage_db_persistence(self):
        # Initial usage check
        initial = _load_token_usage()
        initial_calls = initial.get("api_calls", 0)

        # Update usage
        update_token_usage(prompt=100, completion=50, total=150)
        
        # Reload and check
        updated = _load_token_usage()
        self.assertEqual(updated["prompt_tokens"], 100)
        self.assertEqual(updated["completion_tokens"], 50)
        self.assertEqual(updated["total_tokens"], 150)
        self.assertEqual(updated["api_calls"], initial_calls + 1)

    def test_scheduler_result_db_persistence(self):
        test_result = {"results": [{"symbol": "005930", "decision": "buy"}]}
        recorded_at = "2026-05-29T10:00:00.000000+09:00"
        
        save_scheduler_result("daily_auto", recorded_at, test_result)
        
        loaded = load_latest_scheduler_result()
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded["mode"], "daily_auto")
        self.assertEqual(loaded["recorded_at"], recorded_at)
        self.assertEqual(loaded["result"]["results"][0]["symbol"], "005930")

    def test_auto_approval_db_persistence(self):
        save_auto_approval_state(True)
        self.assertTrue(load_auto_approval_state())
        
        save_auto_approval_state(False)
        self.assertFalse(load_auto_approval_state())

if __name__ == "__main__":
    unittest.main()
