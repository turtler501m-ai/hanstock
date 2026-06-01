import unittest

from fastapi import HTTPException

import src.dashboard as dashboard
from src.db.repository import connect_db, init_db, load_ai_strategies, save_ai_strategies


class AiStrategyLifecycleTests(unittest.TestCase):
    def setUp(self):
        init_db()
        with connect_db() as conn:
            conn.execute("DELETE FROM ai_strategies")
            conn.execute("DELETE FROM ai_strategy_events")
            conn.commit()
        save_ai_strategies([
            {
                "id": "lifecycle_rule",
                "name": "Lifecycle Rule",
                "provider": "none",
                "model": "none",
                "weight": 0.0,
                "description": "Local rule strategy for lifecycle tests",
                "selected": True,
                "status": "draft",
                "profile": {
                    "model": "none",
                    "ai_weight": 0.0,
                    "risk": {
                        "max_risk_per_trade_pct": 1.0,
                        "paper_trading_required_days": 20,
                    },
                    "backtest": {
                        "commission_bps": 15,
                        "slippage_bps": 5,
                        "market_impact_bps": 5,
                    },
                },
            }
        ])

    def test_strategy_context_route_exposes_active_gate(self):
        body = dashboard.get_strategy_context()

        self.assertEqual(body["active_strategy"]["id"], "lifecycle_rule")
        self.assertFalse(body["active_strategy"]["approval_gate"]["ok"])
        self.assertIn("static verification", body["active_strategy"]["approval_gate"]["missing"])
        self.assertTrue(body["safety"]["require_backtest_pass"])

    def test_approval_requires_static_backtest_and_paper_checks(self):
        with self.assertRaises(HTTPException) as blocked:
            dashboard.approve_ai_strategy("lifecycle_rule")
        self.assertEqual(blocked.exception.status_code, 409)

        static_result = dashboard.static_verify_ai_strategy("lifecycle_rule")
        self.assertTrue(static_result["result"]["success"])

        backtest_result = dashboard.backtest_ai_strategy("lifecycle_rule")
        self.assertTrue(backtest_result["result"]["success"])
        self.assertEqual(backtest_result["strategy"]["status"], "backtested")

        start_result = dashboard.start_ai_strategy_paper("lifecycle_rule")
        self.assertEqual(start_result["strategy"]["status"], "paper_running")

        complete_result = dashboard.complete_ai_strategy_paper(
            "lifecycle_rule",
            dashboard.PaperCompletePayload(days=20, observations=20, return_pct=1.2, max_drawdown_pct=2.5),
        )
        self.assertTrue(complete_result["result"]["success"])
        self.assertEqual(complete_result["strategy"]["status"], "paper_passed")

        approved = dashboard.approve_ai_strategy("lifecycle_rule")
        self.assertEqual(approved["strategy"]["status"], "approved")

        loaded = load_ai_strategies()
        found = next(strategy for strategy in loaded if strategy["id"] == "lifecycle_rule")
        self.assertEqual(found["status"], "approved")
        self.assertTrue(found["last_backtested_at"])
        self.assertTrue(found["last_paper_started_at"])
        self.assertTrue(found["last_paper_completed_at"])
        self.assertIn("backtest", found["last_validation_result"])
        self.assertIn("paper", found["last_validation_result"])


if __name__ == "__main__":
    unittest.main()
