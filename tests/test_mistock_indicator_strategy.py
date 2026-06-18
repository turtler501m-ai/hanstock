import unittest
from unittest.mock import patch

from src.mistock.config import config
from src.mistock import strategy
from src.mistock import trader


class MistockIndicatorStrategyTests(unittest.TestCase):
    def setUp(self):
        self.original_model = config.strategy_model
        self.original_min_score = config.indicator_min_score
        self.original_rsi_min = config.indicator_rsi_entry_min
        self.original_rsi_max = config.indicator_rsi_entry_max
        self.original_volume_ratio = config.indicator_volume_ratio

    def tearDown(self):
        config.strategy_model = self.original_model
        config.indicator_min_score = self.original_min_score
        config.indicator_rsi_entry_min = self.original_rsi_min
        config.indicator_rsi_entry_max = self.original_rsi_max
        config.indicator_volume_ratio = self.original_volume_ratio

    def test_macd_rsi_momentum_profile_scores_trend_and_volume(self):
        config.strategy_model = "macd_rsi_momentum"
        config.indicator_rsi_entry_max = 95
        prices = [100 + i * 0.35 for i in range(70)] + [125, 124, 126, 129, 132]
        highs = [price * 1.01 for price in prices]
        volumes = [1000] * (len(prices) - 1) + [1800]

        profile = strategy.strategy_profile(prices, highs, volumes)

        self.assertEqual(profile["strategy_model"], "macd_rsi_momentum")
        self.assertGreaterEqual(profile["score"], 4)
        self.assertIn("above SMA60 trend", profile["reasons"])
        self.assertTrue(any("volume confirmation" in item for item in profile["reasons"]))

    def test_scan_candidates_uses_indicator_min_score_when_defaulted(self):
        config.strategy_model = "macd_rsi_momentum"
        config.indicator_min_score = 5

        with patch("src.mistock.trader._get_kis_client", side_effect=RuntimeError("offline")), \
                patch("src.mistock.strategy.build_scan_universe", return_value=["AAPL"]), \
                patch("src.mistock.trader.get_watchlist", return_value=[]), \
                patch("src.mistock.trader.fetch_history", return_value={"close": [1.0] * 80, "high": [1.0] * 80, "volume": [1.0] * 80}), \
                patch("src.mistock.trader.strategy_profile", return_value={
                    "score": 4,
                    "reasons": ["below threshold"],
                    "price": 1.0,
                    "rsi": 55.0,
                    "rsi2": 50.0,
                    "macd_hist": 0.1,
                    "sma20": 1.0,
                    "sma60": 1.0,
                }), \
                patch("src.mistock.trader.symbol_name", return_value="Apple"), \
                patch("src.mistock.db.execute"):
            result = trader.scan_candidates(limit=1)

        self.assertEqual(result["min_score"], 5)
        self.assertEqual(result["candidates"], [])


if __name__ == "__main__":
    unittest.main()
