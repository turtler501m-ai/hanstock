import unittest
from datetime import datetime
from unittest.mock import patch

from src.dashboard import (
    _account_trades,
    _build_periodic_performance,
    _period_bucket,
    trader,
)


class DashboardPeriodicPerformanceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.original_dry_run = trader.DRY_RUN
        self.original_trading_env = trader.TRADING_ENV

    def tearDown(self) -> None:
        trader.DRY_RUN = self.original_dry_run
        trader.TRADING_ENV = self.original_trading_env

    def test_period_bucket_has_new_keys(self):
        bucket = _period_bucket()
        self.assertIn("cost_of_sold", bucket)
        self.assertIn("realized_pnl_rate", bucket)
        self.assertIn("details", bucket)
        self.assertEqual(bucket["cost_of_sold"], 0)
        self.assertEqual(bucket["realized_pnl_rate"], 0.0)
        self.assertEqual(bucket["details"], [])

    def test_account_trades_filters_dry_run_correctly(self):
        trades = [
            {"ok": 1, "dry_run": 1, "reason": "buy strategy", "symbol": "005930", "action": "buy", "qty": 10, "price": 70000, "ts": "2026-05-27 10:00:00"},
            {"ok": 1, "dry_run": 0, "reason": "sell strategy", "symbol": "005930", "action": "sell", "qty": 10, "price": 75000, "ts": "2026-05-27 11:00:00"},
        ]

        # Case 1: DRY_RUN=false, TRADING_ENV=real -> Bypasses dry_run=1
        trader.DRY_RUN = False
        trader.TRADING_ENV = "real"
        real_trades = _account_trades(trades)
        self.assertEqual(len(real_trades), 1)
        self.assertEqual(real_trades[0]["dry_run"], 0)

        # Case 2: DRY_RUN=true -> Includes dry_run=1
        trader.DRY_RUN = True
        demo_trades = _account_trades(trades)
        self.assertEqual(len(demo_trades), 2)

        # Case 3: TRADING_ENV=demo -> Includes dry_run=1 even if DRY_RUN=false
        trader.DRY_RUN = False
        trader.TRADING_ENV = "demo"
        demo_trades_2 = _account_trades(trades)
        self.assertEqual(len(demo_trades_2), 2)

    def test_build_periodic_performance_computes_correct_realized_rates(self):
        trader.DRY_RUN = True
        trades = [
            # Buy 10 shares of Samsung Electronics at 70,000 KRW (total cost = 700,000)
            {"ok": 1, "dry_run": 1, "reason": "buy", "symbol": "005930", "action": "buy", "qty": 10, "price": 70000, "ts": "2026-05-27 10:00:00"},
            # Sell 5 shares of Samsung Electronics at 77,000 KRW (selling price = 385,000, cost of sold = 350,000, pnl = 35,000, return = 10%)
            {"ok": 1, "dry_run": 1, "reason": "sell", "symbol": "005930", "action": "sell", "qty": 5, "price": 77000, "ts": "2026-05-27 11:00:00"},
        ]

        perf = _build_periodic_performance(trades)
        daily = perf["daily"]
        
        self.assertEqual(len(daily), 1)
        day_bucket = daily[0]
        self.assertEqual(day_bucket["period"], "2026-05-27")
        self.assertEqual(day_bucket["buy_amount"], 700000)
        self.assertEqual(day_bucket["sell_amount"], 385000)
        self.assertEqual(day_bucket["realized_pnl"], 35000)
        self.assertEqual(day_bucket["cost_of_sold"], 350000)
        self.assertEqual(day_bucket["realized_pnl_rate"], 10.0)
        self.assertEqual(day_bucket["net_cashflow"], -315000)
        self.assertEqual(len(day_bucket["details"]), 2)
        sell_detail = day_bucket["details"][1]
        self.assertEqual(sell_detail["symbol"], "005930")
        self.assertEqual(sell_detail["action"], "sell")
        self.assertEqual(sell_detail["amount"], 385000)
        self.assertEqual(sell_detail["realized_pnl"], 35000)
        self.assertEqual(sell_detail["realized_pnl_rate"], 10.0)


if __name__ == "__main__":
    unittest.main()
