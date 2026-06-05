import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.dashboard import app
from src.dashboard.routes import mistock
from src.mistock.config import config as mistock_config
from src.mistock import db as mistock_db
from src.mistock import scheduler as mistock_scheduler
from src.mistock import trader as mistock_trader


class MistockDashboardTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.original_db_path = mistock_config.trade_db_path
        self.original_trading_env = mistock_config.trading_env
        self.original_total_capital = mistock_config.total_capital
        self.original_currency = mistock_config.currency
        object.__setattr__(mistock_config, "trade_db_path", Path(self.tmp.name) / "mistock.sqlite")

    def tearDown(self):
        object.__setattr__(mistock_config, "trade_db_path", self.original_db_path)
        object.__setattr__(mistock_config, "trading_env", self.original_trading_env)
        object.__setattr__(mistock_config, "total_capital", self.original_total_capital)
        object.__setattr__(mistock_config, "currency", self.original_currency)
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

    def test_demo_balance_does_not_mix_paper_cash_when_kis_cash_is_missing(self):
        class FakeClient:
            def get_overseas_balance(self):
                return {
                    "output1": [
                        {
                            "pdno": "AAPL",
                            "prdt_name": "Apple",
                            "cblc_qty13": "2",
                            "avg_unpr3": "100",
                            "ovrs_now_pric1": "150",
                            "frcr_evlu_amt2": "300",
                            "evlu_pfls_amt2": "100",
                        }
                    ],
                    "output2": {},
                    "output3": {},
                }

        object.__setattr__(mistock_config, "trading_env", "demo")
        with patch.object(mistock_trader, "_get_kis_client", return_value=FakeClient()):
            balance = mistock_trader.get_balance()

        self.assertEqual(balance["cash"], 0.0)
        self.assertEqual(balance["stock_eval"], 300.0)
        self.assertEqual(balance["total_eval"], 300.0)

    def test_demo_balance_derives_cash_from_broker_total_when_cash_is_missing(self):
        class FakeClient:
            def get_overseas_balance(self):
                return {
                    "output1": [
                        {
                            "pdno": "MSFT",
                            "prdt_name": "Microsoft",
                            "cblc_qty13": "1",
                            "avg_unpr3": "200",
                            "ovrs_now_pric1": "250",
                            "frcr_evlu_amt2": "250",
                        }
                    ],
                    "output2": {"tot_asst_amt": "1,000"},
                    "output3": {},
                }

        object.__setattr__(mistock_config, "trading_env", "demo")
        with patch.object(mistock_trader, "_get_kis_client", return_value=FakeClient()):
            balance = mistock_trader.get_balance()

        self.assertEqual(balance["cash"], 750.0)
        self.assertEqual(balance["stock_eval"], 250.0)
        self.assertEqual(balance["total_eval"], 1000.0)
        self.assertEqual(balance["broker_total_eval"], 1000.0)

    def test_demo_balance_uses_config_capital_when_kis_account_is_empty(self):
        class FakeClient:
            def get_overseas_balance(self):
                return {
                    "output1": [],
                    "output2": [],
                    "output3": {
                        "dncl_amt": "0",
                        "tot_dncl_amt": "0",
                        "tot_asst_amt": "0",
                        "frcr_use_psbl_amt": "0.00",
                    },
                    "rt_cd": "0",
                    "msg1": "mock account has no rows",
                }

        object.__setattr__(mistock_config, "trading_env", "demo")
        object.__setattr__(mistock_config, "total_capital", 5000.0)
        object.__setattr__(mistock_config, "currency", "USD")
        with patch.object(mistock_trader, "_get_kis_client", return_value=FakeClient()):
            balance = mistock_trader.get_balance()

        self.assertEqual(balance["cash"], 5000.0)
        self.assertEqual(balance["total_eval"], 5000.0)
        self.assertEqual(balance["balance_source"], "demo_config_fallback")

    def test_demo_balance_converts_krw_config_capital_to_usd(self):
        class FakeClient:
            def get_overseas_balance(self):
                return {
                    "output1": [],
                    "output2": [],
                    "output3": {"tot_asst_amt": "0", "frcr_use_psbl_amt": "0.00"},
                    "rt_cd": "0",
                    "msg1": "mock account has no rows",
                }

        object.__setattr__(mistock_config, "trading_env", "demo")
        object.__setattr__(mistock_config, "total_capital", 100000000.0)
        object.__setattr__(mistock_config, "currency", "KRW")
        with patch.object(mistock_trader, "_get_kis_client", return_value=FakeClient()):
            balance = mistock_trader.get_balance()

        self.assertAlmostEqual(balance["cash"], 72463.7681, places=3)
        self.assertEqual(balance["balance_source"], "demo_config_fallback")

    def test_mistock_candidates_include_planned_order_quantity(self):
        scan = {
            "candidates": [
                {
                    "ticker": "AAPL",
                    "symbol": "AAPL",
                    "name": "Apple",
                    "score": 5.0,
                    "price": 100.0,
                    "reasons": ["unit"],
                }
            ],
            "scan_summary": {"scanned": 1, "matched": 1, "scan_error": ""},
            "scanned": 1,
        }

        with patch.object(mistock_trader, "scan_candidates", return_value=scan), \
                patch.object(mistock_trader, "get_balance", return_value={"cash": 1000.0, "balance_source": "test"}):
            result = mistock.mistock_candidates()

        candidate = result["candidates"][0]
        self.assertEqual(candidate["planned_qty"], 8)
        self.assertEqual(candidate["estimated_cost"], 800.0)
        self.assertEqual(result["balance_source"], "test")

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
        with patch("src.dashboard.routes.mistock.threading.Thread") as mock_thread:
            mock_thread_instance = mock_thread.return_value
            with patch.object(mistock_trader, "scan_candidates", return_value={"scanned": 0, "candidates": []}):
                response = mistock.mistock_scheduler_run({"mode": "analysis_only"})
                self.assertIn("result", response)
                mock_thread.assert_called_once()
                mock_thread_instance.start.assert_called_once()

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

    def test_mistock_runtime_order_mode(self):
        # 1. Store initial MISTOCK_DRY_RUN value
        initial_val = mistock_config.dry_run
        target_val = not initial_val

        # 2. Toggle dry_run
        with patch("src.dashboard.routes.mistock._core._write_env_values") as mock_write:
            result = mistock.mistock_runtime_order_mode({"key": "DRY_RUN", "enabled": target_val})
            self.assertTrue(result["ok"])
            self.assertEqual(result["dry_run"], target_val)
            self.assertEqual(mistock_config.dry_run, target_val)
            mock_write.assert_called_once()

            # Toggle back to initial value
            result_true = mistock.mistock_runtime_order_mode({"key": "DRY_RUN", "enabled": initial_val})
            self.assertTrue(result_true["ok"])
            self.assertEqual(result_true["dry_run"], initial_val)
            self.assertEqual(mistock_config.dry_run, initial_val)

    def test_scheduler_marks_broker_order_failure(self):
        order = {
            "symbol": "AAPL",
            "quantity": 1,
            "price": 100.0,
            "reason": "unit test",
        }
        failed_order = {"ok": False, "status": "failed", "msg1": "broker rejected"}

        with patch.object(mistock_trader, "scan_candidates", return_value={"scanned": 1, "candidates": [{"symbol": "AAPL"}]}), \
                patch.object(mistock_trader, "get_balance", return_value={"cash": 1000.0, "total_eval": 1000.0}), \
                patch.object(mistock_trader, "signals", return_value=[]), \
                patch.object(mistock_trader, "build_orders", return_value=[order]), \
                patch.object(mistock_trader, "place_paper_order", return_value=failed_order), \
                patch.object(mistock_db, "get_setting", return_value="true"), \
                patch.object(mistock_scheduler, "send_mistock_slack"):
            result = mistock_scheduler.run_mistock_scheduled_cycle(mode="execute")

        self.assertFalse(result["ok"])
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["errors"][0]["symbol"], "AAPL")
        self.assertEqual(result["errors"][0]["message"], "broker rejected")


if __name__ == "__main__":
    unittest.main()
