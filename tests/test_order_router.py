import unittest
from unittest.mock import patch

from src.config import config
from src.strategy import router


class OrderRouterTests(unittest.TestCase):
    def test_direct_demo_submission_records_broker_tracking_fields(self):
        original = {
            "dry_run": config.dry_run,
            "trading_env": config.trading_env,
            "enable_live_trading": config.enable_live_trading,
            "require_approval": config.require_approval,
        }

        class FakeApi:
            def get_balance(self):
                return {"output1": [{"pdno": "005930", "hldg_qty": "3"}]}

            def place_order(self, symbol, action, price, qty):
                return {"rt_cd": "0", "msg1": "accepted", "output": {"ODNO": "D98765"}}

        saved = []
        try:
            config.dry_run = False
            config.trading_env = "demo"
            config.enable_live_trading = False
            config.require_approval = False

            order_router = router.OrderRouter(FakeApi())
            with patch.object(router, "save_decision_log"), patch.object(
                router, "save_trade", side_effect=lambda *args, **kwargs: saved.append((args, kwargs))
            ):
                result = order_router.route("005930", "Samsung", "buy", 1, 70000, "test", {})

            self.assertTrue(result["ok"])
            self.assertEqual(len(saved), 1)
            kwargs = saved[0][1]
            self.assertEqual(kwargs["broker_result"]["output"]["ODNO"], "D98765")
            self.assertEqual(kwargs["order_status"], "submitted")
            self.assertEqual(kwargs["response_msg"], "accepted")
            self.assertEqual(kwargs["filled_qty"], 0)
            self.assertEqual(kwargs["filled_price"], 0)
            self.assertEqual(kwargs["pre_order_qty"], 3)
        finally:
            config.dry_run = original["dry_run"]
            config.trading_env = original["trading_env"]
            config.enable_live_trading = original["enable_live_trading"]
            config.require_approval = original["require_approval"]


if __name__ == "__main__":
    unittest.main()
