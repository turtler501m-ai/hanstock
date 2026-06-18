import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from fastapi import HTTPException

from src.dashboard import app
from src.dashboard.routes import narrative_momentum
from src.strategy.narrative_momentum import save_json_file


class NarrativeMomentumDashboardTest(unittest.TestCase):
    def test_routes_are_registered(self):
        paths = {getattr(route, "path", "") for route in app.routes}
        self.assertIn("/narrative-momentum", paths)
        self.assertIn("/api/narrative-momentum/status", paths)
        self.assertIn("/api/narrative-momentum/latest", paths)
        self.assertIn("/api/narrative-momentum/scan", paths)
        self.assertIn("/api/narrative-momentum/history", paths)
        self.assertIn("/api/narrative-momentum/theme-map", paths)

    def test_template_links_dedicated_assets(self):
        with open("web/templates/narrative_momentum.html", encoding="utf-8") as handle:
            template = handle.read()
        with open("web/static/js/narrative_momentum.js", encoding="utf-8") as handle:
            script = handle.read()
        self.assertIn("/static/css/narrative_momentum.css", template)
        self.assertIn("/static/js/narrative_momentum.js", template)
        self.assertIn("narrative-history-editor", template)
        self.assertIn("가격/수량", template)
        self.assertIn("/api/narrative-momentum", script)
        self.assertIn("/api/narrative-momentum/history", script)
        self.assertIn("narrative-price", script)
        self.assertIn("지정가와 수량", script)

    def test_save_history_writes_utf8_json(self):
        payload = {
            "history": [
                {
                    "date": "2026-06-18",
                    "dominant_narratives": [
                        {
                            "theme": "AI 반도체 투자 확대",
                            "strength": 88,
                            "sentiment": "bullish",
                            "direction": "rising",
                            "affected_sectors": ["반도체"],
                        }
                    ],
                }
            ]
        }
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "narrative_history.json"
            with patch.object(narrative_momentum, "NARRATIVE_HISTORY_PATH", path):
                result = narrative_momentum.save_narrative_momentum_history(payload)
            self.assertTrue(result["ok"])
            text = path.read_text(encoding="utf-8")
        self.assertIn("AI 반도체 투자 확대", text)

    def test_queue_approval_rejects_ticker_not_in_current_signals(self):
        history = [
            {
                "date": "2026-06-18",
                "dominant_narratives": [
                    {
                        "theme": "AI 반도체 투자 확대",
                        "strength": 88,
                        "sentiment": "bullish",
                        "direction": "rising",
                        "affected_sectors": ["반도체"],
                    }
                ],
            }
        ]
        theme_map = {"반도체": [{"ticker": "005930", "name": "삼성전자"}]}
        with TemporaryDirectory() as tmp:
            history_path = Path(tmp) / "narrative_history.json"
            theme_path = Path(tmp) / "theme_map.json"
            save_json_file(history_path, history)
            save_json_file(theme_path, theme_map)
            with patch.object(narrative_momentum, "NARRATIVE_HISTORY_PATH", history_path), \
                    patch.object(narrative_momentum, "THEME_MAP_PATH", theme_path), \
                    patch.object(narrative_momentum, "_has_pending_buy", return_value=False), \
                    patch.object(narrative_momentum, "_create_approval_row", return_value=10):
                with self.assertRaises(HTTPException) as ctx:
                    narrative_momentum.queue_narrative_approval(
                        {"ticker": "000660", "name": "SK하이닉스", "score": 99, "qty": 1, "price": 100000}
                    )
        self.assertEqual(ctx.exception.status_code, 404)

    def test_queue_approval_accepts_current_signal_with_manual_price(self):
        history = [
            {
                "date": "2026-06-18",
                "dominant_narratives": [
                    {
                        "theme": "AI 반도체 투자 확대",
                        "strength": 88,
                        "sentiment": "bullish",
                        "direction": "rising",
                        "affected_sectors": ["반도체"],
                    }
                ],
            }
        ]
        theme_map = {"반도체": [{"ticker": "005930", "name": "삼성전자"}]}
        with TemporaryDirectory() as tmp:
            history_path = Path(tmp) / "narrative_history.json"
            theme_path = Path(tmp) / "theme_map.json"
            save_json_file(history_path, history)
            save_json_file(theme_path, theme_map)
            with patch.object(narrative_momentum, "NARRATIVE_HISTORY_PATH", history_path), \
                    patch.object(narrative_momentum, "THEME_MAP_PATH", theme_path), \
                    patch.object(narrative_momentum, "_has_pending_buy", return_value=False), \
                    patch.object(narrative_momentum, "_create_approval_row", return_value=10) as create:
                result = narrative_momentum.queue_narrative_approval(
                    {"ticker": "005930", "name": "임의명", "score": 99, "qty": 2, "price": 80000}
                )
        self.assertEqual(result["id"], 10)
        self.assertEqual(create.call_args.args[0]["name"], "삼성전자")
        self.assertEqual(create.call_args.args[0]["qty"], 2)
        self.assertEqual(create.call_args.args[0]["price"], 80000)

    def test_save_candidates_skips_zero_price_signals(self):
        with patch.object(narrative_momentum, "save_scanned_candidate", return_value=1) as save:
            saved = narrative_momentum._save_candidates(
                [{"ticker": "005930", "name": "삼성전자", "score": 90, "current_price": 0, "reasons": []}]
            )
        self.assertEqual(saved, 0)
        save.assert_not_called()


if __name__ == "__main__":
    unittest.main()
