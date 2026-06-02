import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.dashboard import app
from src.dashboard.routes import mistock
from src.mistock.config import config as mistock_config
from src.mistock import db as mistock_db
from src.mistock import trader as mistock_trader


class MistockDashboardTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.original_db_path = mistock_config.trade_db_path
        object.__setattr__(mistock_config, "trade_db_path", Path(self.tmp.name) / "mistock.sqlite")

    def tearDown(self):
        object.__setattr__(mistock_config, "trade_db_path", self.original_db_path)
        self.tmp.cleanup()

    def test_mistock_routes_are_registered(self):
        paths = {getattr(route, "path", "") for route in app.routes}

        self.assertIn("/mistock", paths)
        self.assertIn("/api/mistock/balance", paths)
        self.assertIn("/api/mistock/approvals/{approval_id}/approve", paths)
        self.assertIn("/api/mistock/orders/cancel", paths)
        self.assertIn("/api/mistock/orders/revise", paths)

    def test_mistock_uses_separate_runtime_database(self):
        health = mistock.mistock_health()
        watchlist = mistock.mistock_watchlist()

        self.assertTrue(health["ok"])
        self.assertEqual(health["trading_env"], "paper")
        self.assertTrue(str(mistock_config.trade_db_path).endswith("mistock.sqlite"))
        self.assertGreaterEqual(len(watchlist["symbols"]), 1)
        self.assertTrue(mistock_config.trade_db_path.exists())

    def test_paper_approval_executes_against_mistock_holdings(self):
        mistock_trader.add_watchlist("AAPL", "Apple")
        approval = mistock.mistock_create_approval({
            "symbol": "AAPL",
            "name": "Apple",
            "action": "buy",
            "qty": 2,
            "price": 100,
            "reason": "unit test",
            "source": "test",
        })

        with patch.object(mistock_trader, "quote", return_value={"current": 100.0, "ask1": 100.0, "bid1": 100.0}):
            result = mistock.mistock_approve(approval["id"])
            balance = mistock.mistock_balance()
        trades = mistock.mistock_trades(limit=5)

        self.assertTrue(result["ok"])
        self.assertEqual(result["status"], "executed")
        self.assertEqual(balance["cash"], mistock_config.total_capital - 200)
        self.assertEqual(balance["holdings"][0]["symbol"], "AAPL")
        self.assertEqual(len(trades["trades"]), 1)

    def test_mistock_settings_and_action_endpoints_are_available(self):
        env_result = mistock.mistock_update_env({"values": {"MISTOCK_TOTAL_CAPITAL": "100000"}})
        strategies = mistock.mistock_ai_strategies()["strategies"]
        strategy_id = strategies[0]["id"]

        self.assertTrue(env_result["ok"])
        self.assertTrue(env_result["requires_restart"])
        self.assertTrue(mistock.mistock_static_verify(strategy_id)["ok"])
        self.assertTrue(mistock.mistock_api_verify(strategy_id)["ok"])
        self.assertTrue(mistock.mistock_backtest(strategy_id)["ok"])
        self.assertTrue(mistock.mistock_paper_start(strategy_id)["ok"])
        self.assertTrue(mistock.mistock_paper_complete(strategy_id, {"days": 20})["ok"])
        self.assertEqual(mistock.mistock_strategy_approve(strategy_id)["status"], "approved")

        watchlist_result = mistock.mistock_watchlist_toggle_auto({"enabled": True, "threshold": 4})
        self.assertTrue(watchlist_result["enabled"])
        self.assertEqual(watchlist_result["threshold"], 4.0)
        self.assertTrue(mistock.mistock_trades_sync()["ok"])
        with patch.object(mistock_trader, "scan_candidates", return_value={"scanned": 0, "candidates": []}):
            self.assertIn("result", mistock.mistock_scheduler_run({"mode": "analysis_only"}))

    def test_mistock_easy_preset_uses_nasdaq_profile_and_selects_strategy(self):
        result = mistock.mistock_apply_ai_strategy_preset("aggressive")
        strategies = mistock.mistock_ai_strategies()["strategies"]
        selected = [item for item in strategies if item.get("selected")]

        self.assertTrue(result["ok"])
        self.assertEqual(result["preset"], "aggressive")
        self.assertEqual(len(selected), 1)
        self.assertEqual(selected[0]["id"], result["strategy"]["id"])
        self.assertEqual(selected[0]["status"], "approved")
        self.assertEqual(selected[0]["profile"]["market"], "NASDAQ")
        self.assertEqual(selected[0]["profile"]["universe"], "NASDAQ100")
        context = mistock.mistock_strategy_context()
        self.assertEqual(context["active_strategy"]["id"], result["strategy"]["id"])
        self.assertIn("backtest", context["active_strategy"]["validation"]["checks"])


if __name__ == "__main__":
    unittest.main()
