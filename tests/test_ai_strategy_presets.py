import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import src.dashboard as dashboard
from src.dashboard.routes import stock
from src.db import repository


class AiStrategyPresetTests(unittest.TestCase):
    def test_hanstock_easy_preset_creates_selected_approved_strategy(self):
        original_db_path = dashboard.trader.config.trade_db_path
        try:
            with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
                dashboard.trader.config.trade_db_path = str(Path(tmpdir) / "trades.sqlite")
                backup_path = Path(tmpdir) / "ai_strategies.json"
                with patch.object(repository, "AI_STRATEGIES_FILE", backup_path):
                    result = stock.apply_ai_strategy_preset("balanced")
                    strategies = repository.load_ai_strategies()
        finally:
            dashboard.trader.config.trade_db_path = original_db_path

        selected = [item for item in strategies if item.get("selected")]
        self.assertTrue(result["ok"])
        self.assertEqual(result["preset"], "balanced")
        self.assertEqual(len(selected), 1)
        self.assertEqual(selected[0]["id"], result["strategy"]["id"])
        self.assertEqual(selected[0]["status"], "approved")
        self.assertEqual(selected[0]["provider"], "none")
        self.assertEqual(selected[0]["profile"]["risk"]["paper_trading_required_days"], 0)

    def test_unknown_hanstock_preset_is_rejected(self):
        with self.assertRaises(Exception):
            stock.apply_ai_strategy_preset("unknown")


if __name__ == "__main__":
    unittest.main()
