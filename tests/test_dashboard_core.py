import tempfile
import unittest
import sqlite3
from datetime import datetime
from unittest.mock import patch

import src.dashboard as dashboard
from src.dashboard import _parse_balance, _portfolio_totals


class MemoryCachePath:
    def __init__(self):
        self.content = None
        self.parent = self

    def mkdir(self, parents=False, exist_ok=False):
        return None

    def exists(self):
        return self.content is not None

    def write_text(self, text, encoding=None):
        self.content = text

    def read_text(self, encoding=None):
        return self.content


class MemoryTextPath:
    def __init__(self, content=""):
        self.content = content

    def exists(self):
        return True

    def read_text(self, encoding=None):
        return self.content

    def write_text(self, text, encoding=None):
        self.content = text


class DashboardCoreTests(unittest.TestCase):
    def test_parse_balance_uses_holding_eval_amount(self):
        parsed = _parse_balance({
            "output1": [{
                "pdno": "005930",
                "prdt_name": "Samsung",
                "hldg_qty": "10",
                "prpr": "0",
                "evlu_amt": "700000",
                "evlu_pfls_amt": "-10000",
                "evlu_pfls_rt": "-1.41",
            }],
            "output2": [{
                "dnca_tot_amt": "1000000",
                "prvs_rcdl_excc_amt": "200000",
                "scts_evlu_amt": "700000",
                "tot_evlu_amt": "900000",
                "evlu_pfls_smtl_amt": "-10000",
            }],
        })

        self.assertEqual(parsed["holdings"][0]["value"], 700000)
        self.assertEqual(parsed["holdings"][0]["price"], 70000)
        self.assertEqual(parsed["stock_eval"], 700000)
        self.assertEqual(parsed["cash"], 200000)
        self.assertEqual(parsed["total_eval"], 900000)
        self.assertLessEqual(parsed["cash_ratio"], 1.0)

    def test_portfolio_totals_clamps_cash_ratio(self):
        totals = _portfolio_totals(
            cash=10_000_000,
            summary_total=9_937_130,
            holdings=[{"value": 2_000_000}],
        )

        self.assertEqual(totals["stock_eval"], 2_000_000)
        self.assertEqual(totals["total_eval"], 9_937_130)
        self.assertGreater(totals["cash_ratio"], 0)
        self.assertLessEqual(totals["cash_ratio"], 1.0)

    def test_balance_cache_is_scoped_to_account(self):
        original_cache = dashboard.BALANCE_CACHE
        original_account = dashboard.trader.config.kistock_account
        try:
            dashboard.BALANCE_CACHE = MemoryCachePath()
            dashboard.trader.config.kistock_account = "1111111101"
            dashboard._save_balance_cache({"output1": [], "output2": []})

            dashboard.trader.config.kistock_account = "2222222201"
            self.assertIsNone(dashboard._load_balance_cache())

            dashboard.trader.config.kistock_account = "1111111101"
            self.assertIsNotNone(dashboard._load_balance_cache())
        finally:
            dashboard.BALANCE_CACHE = original_cache
            dashboard.trader.config.kistock_account = original_account

    def test_env_writer_preserves_comments_and_updates_allowed_keys(self):
        path = MemoryTextPath("# KIS\nTRADING_ENV=demo\nDRY_RUN=true\nMAX_POSITIONS=10 # 최대보유주식종목\n")
        dashboard._write_env_values({"TRADING_ENV": "real", "MAX_POSITIONS": "5"}, path)

        self.assertIn("# KIS", path.content)
        self.assertIn("TRADING_ENV=real", path.content)
        self.assertIn("DRY_RUN=true", path.content)
        self.assertIn("MAX_POSITIONS=5 # 최대보유주식종목", path.content)

    def test_env_reader_strips_inline_comments_from_numbers(self):
        path = MemoryTextPath("MAX_POSITIONS=10 # 최대보유주식종목\nACTIVE_MODEL_VERSION=v1\n")

        values = dashboard._read_env_values(path)

        self.assertEqual(values["MAX_POSITIONS"], "10")
        self.assertEqual(dashboard._validate_env_value("MAX_POSITIONS", "10 # 최대보유주식종목"), "10")

    def test_kis_ops_routes_are_registered(self):
        paths = {getattr(route, "path", "") for route in dashboard.app.routes}

        self.assertIn("/api/kis/condition-search/list", paths)
        self.assertIn("/api/kis/condition-search/result", paths)
        self.assertIn("/api/kis/websocket/status", paths)
        self.assertIn("/api/kis/websocket/start", paths)
        self.assertIn("/api/kis/websocket/stop", paths)
        self.assertIn("/api/kis/websocket/subscribe", paths)
        self.assertIn("/api/kis/orders/cancel", paths)
        self.assertIn("/api/kis/orders/revise", paths)
        self.assertIn("/api/kis/rehearsal", paths)

    def test_kis_env_settings_apply_without_restart(self):
        original_env_path = dashboard.ENV_PATH
        original_values = {
            "kistock_hts_id": getattr(dashboard.trader.config, "kistock_hts_id", ""),
            "kis_websocket_enabled": getattr(dashboard.trader.config, "kis_websocket_enabled", False),
            "kis_condition_search_enabled": getattr(dashboard.trader.config, "kis_condition_search_enabled", False),
            "kis_condition_user_id": getattr(dashboard.trader.config, "kis_condition_user_id", ""),
            "kis_condition_seq": getattr(dashboard.trader.config, "kis_condition_seq", ""),
            "kis_condition_name": getattr(dashboard.trader.config, "kis_condition_name", ""),
        }
        try:
            dashboard.ENV_PATH = MemoryTextPath("")
            result = dashboard.update_env_settings({
                "values": {
                    "KISTOCK_HTS_ID": "hts-user",
                    "KIS_WEBSOCKET_ENABLED": "true",
                    "KIS_CONDITION_SEARCH_ENABLED": "true",
                    "KIS_CONDITION_USER_ID": "condition-user",
                    "KIS_CONDITION_SEQ": "001",
                    "KIS_CONDITION_NAME": "breakout",
                    "MISTOCK_EXCHANGE_MAP": "BRK.B=NYSE",
                }
            })

            self.assertTrue(result["ok"])
            self.assertEqual(dashboard.trader.config.kistock_hts_id, "hts-user")
            self.assertTrue(dashboard.trader.config.kis_websocket_enabled)
            self.assertTrue(dashboard.trader.config.kis_condition_search_enabled)
            self.assertEqual(dashboard.trader.config.kis_condition_user_id, "condition-user")
            self.assertEqual(dashboard.trader.config.kis_condition_seq, "001")
            self.assertEqual(dashboard.trader.config.kis_condition_name, "breakout")
        finally:
            dashboard.ENV_PATH = original_env_path
            for key, value in original_values.items():
                setattr(dashboard.trader.config, key, value)

    def test_runtime_order_mode_updates_apply_without_restart(self):
        original_env_path = dashboard.ENV_PATH
        original_trading_env = dashboard.trader.TRADING_ENV
        original_dry_run = dashboard.trader.DRY_RUN
        original_enable_live = dashboard.trader.ENABLE_LIVE_TRADING
        original_order_submission = dashboard.trader.ORDER_SUBMISSION_ENABLED
        original_real_orders = dashboard.trader.REAL_ORDERS_ENABLED
        original_config_values = {
            "trading_env": dashboard.trader.config.trading_env,
            "dry_run": dashboard.trader.config.dry_run,
            "enable_live_trading": dashboard.trader.config.enable_live_trading,
        }
        try:
            path = MemoryTextPath("TRADING_ENV=demo\nDRY_RUN=true\nENABLE_LIVE_TRADING=false\n")
            dashboard.ENV_PATH = path
            dashboard.trader.TRADING_ENV = "demo"
            dashboard.trader.DRY_RUN = True
            dashboard.trader.ENABLE_LIVE_TRADING = False
            dashboard.trader.REAL_ORDERS_ENABLED = False
            dashboard.trader.ORDER_SUBMISSION_ENABLED = False
            dashboard.trader.config.trading_env = "demo"
            dashboard.trader.config.dry_run = True
            dashboard.trader.config.enable_live_trading = False

            result = dashboard.set_runtime_order_mode({"key": "DRY_RUN", "enabled": False})
            self.assertFalse(result["dry_run"])
            self.assertTrue(result["order_submission_enabled"])
            self.assertIn("DRY_RUN=false", path.content)

            with self.assertRaises(dashboard.HTTPException):
                dashboard.set_runtime_order_mode({"key": "REAL_ORDERS_ENABLED", "enabled": True})
        finally:
            dashboard.ENV_PATH = original_env_path
            dashboard.trader.TRADING_ENV = original_trading_env
            dashboard.trader.DRY_RUN = original_dry_run
            dashboard.trader.ENABLE_LIVE_TRADING = original_enable_live
            dashboard.trader.ORDER_SUBMISSION_ENABLED = original_order_submission
            dashboard.trader.REAL_ORDERS_ENABLED = original_real_orders
            dashboard.trader.config.trading_env = original_config_values["trading_env"]
            dashboard.trader.config.dry_run = original_config_values["dry_run"]
            dashboard.trader.config.enable_live_trading = original_config_values["enable_live_trading"]

    def test_secret_env_values_are_masked_for_response(self):
        self.assertEqual(dashboard._mask_env_value("1234567801"), "12******01")

    def test_env_settings_do_not_return_secret_values(self):
        original_env_path = dashboard.ENV_PATH
        try:
            dashboard.ENV_PATH = MemoryTextPath(
                "KISTOCK_APP_KEY=app-key-secret\n"
                "KISTOCK_ACCOUNT=1234567801\n"
                "TRADING_ENV=demo\n"
            )
            with patch("src.utils.exchange_rate.get_usd_krw_rate", return_value=1380.0):
                data = dashboard.get_env_settings()
            fields = {field["key"]: field for field in data["fields"]}

            self.assertEqual(fields["KISTOCK_APP_KEY"]["value"], "")
            self.assertEqual(fields["KISTOCK_APP_KEY"]["masked"], "ap**********et")
            self.assertTrue(fields["KISTOCK_APP_KEY"]["has_value"])
            self.assertEqual(fields["KISTOCK_ACCOUNT"]["value"], "")
            self.assertEqual(fields["KISTOCK_ACCOUNT"]["masked"], "12******01")
        finally:
            dashboard.ENV_PATH = original_env_path

    def test_env_settings_labels_are_korean_for_ai_fields(self):
        original_env_path = dashboard.ENV_PATH
        try:
            dashboard.ENV_PATH = MemoryTextPath("AI_STRATEGY_ENABLED=false\nOPENAI_MODEL=gpt-5-mini\n")
            data = dashboard.get_env_settings()
            labels = {field["key"]: field["label"] for field in data["fields"]}

            self.assertEqual(labels["AI_STRATEGY_ENABLED"], "AI 전략 사용")
            self.assertEqual(labels["OPENAI_MODEL"], "OpenAI 모델")
            self.assertEqual(labels["TRADING_ENV"], "거래 환경")
        finally:
            dashboard.ENV_PATH = original_env_path

    def test_env_settings_use_runtime_defaults_for_missing_ai_values(self):
        original_env_path = dashboard.ENV_PATH
        original_ai_enabled = dashboard.trader.config.ai_strategy_enabled
        original_backtest = dashboard.trader.config.ai_require_backtest_pass
        original_model = dashboard.trader.config.openai_model
        try:
            dashboard.ENV_PATH = MemoryTextPath("TRADING_ENV=demo\n")
            dashboard.trader.config.ai_strategy_enabled = False
            dashboard.trader.config.ai_require_backtest_pass = True
            dashboard.trader.config.openai_model = "gpt-5-mini"

            data = dashboard.get_env_settings()
            values = {field["key"]: field["value"] for field in data["fields"]}

            self.assertEqual(values["AI_STRATEGY_ENABLED"], "false")
            self.assertEqual(values["AI_REQUIRE_BACKTEST_PASS"], "true")
            self.assertEqual(values["OPENAI_MODEL"], "gpt-5-mini")
        finally:
            dashboard.ENV_PATH = original_env_path
            dashboard.trader.config.ai_strategy_enabled = original_ai_enabled
            dashboard.trader.config.ai_require_backtest_pass = original_backtest
            dashboard.trader.config.openai_model = original_model

    def test_config_response_masks_account(self):
        original_account = dashboard.trader.config.kistock_account
        try:
            dashboard.trader.config.kistock_account = "1234567801"
            config = dashboard.get_config()
            self.assertEqual(config["kistock_account"], "12******01")
            self.assertEqual(config["ai_analysis"]["account"], "12******01")
            self.assertEqual(config["ai_analysis"]["account_priority"], "current_kis_account")
            self.assertEqual(config["ai_analysis"]["provider"], "openai_responses")
        finally:
            dashboard.trader.config.kistock_account = original_account

    def test_demo_trading_readiness_requires_demo_submission_without_live_switch(self):
        original_values = {
            "trading_env": dashboard.trader.TRADING_ENV,
            "dry_run": dashboard.trader.DRY_RUN,
            "enable_live_trading": dashboard.trader.ENABLE_LIVE_TRADING,
            "order_submission_enabled": dashboard.trader.ORDER_SUBMISSION_ENABLED,
            "real_orders_enabled": dashboard.trader.REAL_ORDERS_ENABLED,
            "account": dashboard.trader.config.kistock_account,
        }
        original_required_env_missing = dashboard._required_env_missing
        try:
            dashboard.trader.TRADING_ENV = "demo"
            dashboard.trader.DRY_RUN = False
            dashboard.trader.ENABLE_LIVE_TRADING = False
            dashboard.trader.ORDER_SUBMISSION_ENABLED = True
            dashboard.trader.REAL_ORDERS_ENABLED = False
            dashboard.trader.config.kistock_account = "1234567801"
            dashboard._required_env_missing = lambda: []

            readiness = dashboard.get_demo_trading_readiness()

            self.assertTrue(readiness["ready"])
            self.assertTrue(all(check["ok"] for check in readiness["checks"] if check["critical"]))
            self.assertFalse(readiness["real_orders_enabled"])
        finally:
            dashboard.trader.TRADING_ENV = original_values["trading_env"]
            dashboard.trader.DRY_RUN = original_values["dry_run"]
            dashboard.trader.ENABLE_LIVE_TRADING = original_values["enable_live_trading"]
            dashboard.trader.ORDER_SUBMISSION_ENABLED = original_values["order_submission_enabled"]
            dashboard.trader.REAL_ORDERS_ENABLED = original_values["real_orders_enabled"]
            dashboard.trader.config.kistock_account = original_values["account"]
            dashboard._required_env_missing = original_required_env_missing

    def test_env_update_applies_strategy_settings_without_restart(self):
        original_env_path = dashboard.ENV_PATH
        original_total_capital = dashboard.trader.TOTAL_CAPITAL
        original_max_single_weight = dashboard.trader.MAX_SINGLE_WEIGHT
        original_config_total_capital = dashboard.trader.config.total_capital
        original_config_max_single_weight = dashboard.trader.config.max_single_weight
        try:
            path = MemoryTextPath("TOTAL_CAPITAL=10000000\nMAX_SINGLE_WEIGHT=0.3\n")
            dashboard.ENV_PATH = path

            result = dashboard.update_env_settings({
                "values": {
                    "TOTAL_CAPITAL": "12000000",
                    "MAX_SINGLE_WEIGHT": "0.25",
                }
            })

            self.assertFalse(result["requires_restart"])
            self.assertEqual(dashboard.trader.TOTAL_CAPITAL, 12000000.0)
            self.assertEqual(dashboard.trader.config.total_capital, 12000000.0)
            self.assertEqual(dashboard.trader.MAX_SINGLE_WEIGHT, 0.25)
            self.assertEqual(dashboard.trader.config.max_single_weight, 0.25)
            self.assertIn("TOTAL_CAPITAL=12000000", path.content)
            self.assertIn("MAX_SINGLE_WEIGHT=0.25", path.content)
        finally:
            dashboard.ENV_PATH = original_env_path
            dashboard.trader.TOTAL_CAPITAL = original_total_capital
            dashboard.trader.MAX_SINGLE_WEIGHT = original_max_single_weight
            dashboard.trader.config.total_capital = original_config_total_capital
            dashboard.trader.config.max_single_weight = original_config_max_single_weight

    def test_env_update_saves_openai_strategy_settings(self):
        original_env_path = dashboard.ENV_PATH
        original_ai_enabled = dashboard.trader.config.ai_strategy_enabled
        original_openai_key = dashboard.trader.config.openai_api_key
        original_openai_model = dashboard.trader.config.openai_model
        try:
            path = MemoryTextPath("AI_STRATEGY_ENABLED=false\nOPENAI_MODEL=gpt-5-mini\n")
            dashboard.ENV_PATH = path

            result = dashboard.update_env_settings({
                "values": {
                    "AI_STRATEGY_ENABLED": "true",
                    "OPENAI_API_KEY": "sk-test-openai-key",
                    "OPENAI_MODEL": "gpt-5-mini",
                }
            })

            self.assertFalse(result["requires_restart"])
            self.assertTrue(dashboard.trader.config.ai_strategy_enabled)
            self.assertEqual(dashboard.trader.config.openai_api_key, "sk-test-openai-key")
            self.assertEqual(dashboard.trader.config.openai_model, "gpt-5-mini")
            self.assertIn("AI_STRATEGY_ENABLED=true", path.content)
            self.assertIn("OPENAI_API_KEY=sk-test-openai-key", path.content)
            self.assertIn("OPENAI_MODEL=gpt-5-mini", path.content)
        finally:
            dashboard.ENV_PATH = original_env_path
            dashboard.trader.config.ai_strategy_enabled = original_ai_enabled
            dashboard.trader.config.openai_api_key = original_openai_key
            dashboard.trader.config.openai_model = original_openai_model

    def test_kis_account_validation_accepts_8_or_10_digits(self):
        self.assertEqual(dashboard._validate_env_value("KISTOCK_ACCOUNT", "12345678"), "12345678")
        self.assertEqual(dashboard._validate_env_value("KISTOCK_ACCOUNT", "12345678-01"), "1234567801")
        with self.assertRaises(dashboard.HTTPException):
            dashboard._validate_env_value("KISTOCK_ACCOUNT", "1234567")

    def test_required_env_missing_accepts_8_digit_account(self):
        original_account = dashboard.trader.config.kistock_account
        try:
            dashboard.trader.config.kistock_account = "12345678"
            missing = dashboard._required_env_missing()
            self.assertNotIn("KISTOCK_ACCOUNT_FORMAT", missing)
        finally:
            dashboard.trader.config.kistock_account = original_account

    def test_auto_approval_state_can_toggle(self):
        original_state = dashboard.AUTO_APPROVAL_STATE
        try:
            dashboard.AUTO_APPROVAL_STATE = MemoryCachePath()
            self.assertFalse(dashboard._auto_approval_enabled())

            dashboard._save_auto_approval(True)
            self.assertTrue(dashboard._auto_approval_enabled())

            dashboard._save_auto_approval(False)
            self.assertFalse(dashboard._auto_approval_enabled())
        finally:
            dashboard.AUTO_APPROVAL_STATE = original_state

    def test_candidate_cache_invalidates_when_strategy_profile_changes(self):
        original_cache = dashboard.CANDIDATE_CACHE
        try:
            dashboard.CANDIDATE_CACHE = MemoryCachePath()
            strategy_v1 = {
                "id": "strategy_a",
                "strategy_version": 1,
                "profile_hash": "hash-a",
            }
            strategy_v2 = {
                "id": "strategy_a",
                "strategy_version": 2,
                "profile_hash": "hash-b",
            }

            with patch("src.db.repository.load_ai_strategies", return_value=[strategy_v1]):
                dashboard._save_candidate_cache(2, [{"ticker": "005930"}], [], 1, "strategy_a", "opt")
                cached = dashboard._load_candidate_cache(2, "strategy_a", "opt")
                self.assertIsNotNone(cached)

            with patch("src.db.repository.load_ai_strategies", return_value=[strategy_v2]):
                self.assertIsNone(dashboard._load_candidate_cache(2, "strategy_a", "opt"))
        finally:
            dashboard.CANDIDATE_CACHE = original_cache

    def test_enabling_auto_approval_processes_pending_orders(self):
        original_state = dashboard.AUTO_APPROVAL_STATE
        original_db_path = dashboard.trader.config.trade_db_path
        original_get_api = dashboard._get_api
        original_save_trade = dashboard.trader.save_trade
        original_slack_order = dashboard._slack_order
        original_dry_run = dashboard.trader.DRY_RUN
        original_order_submission = dashboard.trader.ORDER_SUBMISSION_ENABLED

        class _FakeAPI:
            def place_order(self, symbol, order_type, price, qty):
                return {"rt_cd": "0", "msg1": "DRY_RUN"}

        try:
            with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
                dashboard.AUTO_APPROVAL_STATE = MemoryCachePath()
                dashboard.trader.config.trade_db_path = f"{tmpdir}/trades.sqlite"
                dashboard._get_api = lambda: _FakeAPI()
                dashboard.trader.save_trade = lambda *args, **kwargs: None
                dashboard._slack_order = lambda *args, **kwargs: None
                dashboard.trader.DRY_RUN = True
                dashboard.trader.ORDER_SUBMISSION_ENABLED = False

                created = dashboard.create_approval({
                    "symbol": "005930",
                    "name": "Samsung",
                    "action": "buy",
                    "qty": 1,
                    "price": 70000,
                    "reason": "test",
                    "source": "test",
                })
                self.assertEqual(created["status"], "pending")

                result = dashboard.set_auto_approval({"enabled": True})
                self.assertEqual(result["processed_count"], 1)

                approvals = dashboard.get_approvals()["approvals"]
                self.assertEqual(approvals[0]["status"], "executed")
                self.assertEqual(approvals[0]["response_msg"], "DRY_RUN")
        finally:
            dashboard.AUTO_APPROVAL_STATE = original_state
            dashboard.trader.config.trade_db_path = original_db_path
            dashboard._get_api = original_get_api
            dashboard.trader.save_trade = original_save_trade
            dashboard._slack_order = original_slack_order
            dashboard.trader.DRY_RUN = original_dry_run
            dashboard.trader.ORDER_SUBMISSION_ENABLED = original_order_submission

    def test_approval_execution_is_claimed_once_and_records_broker_result(self):
        original_db_path = dashboard.trader.config.trade_db_path
        original_get_api = dashboard._get_api
        original_slack_order = dashboard._slack_order
        original_auto_approval_state = dashboard.AUTO_APPROVAL_STATE
        original_dry_run = dashboard.trader.DRY_RUN
        original_trading_env = dashboard.trader.TRADING_ENV
        original_order_submission = dashboard.trader.ORDER_SUBMISSION_ENABLED

        class _FakeAPI:
            def __init__(self):
                self.calls = 0

            def place_order(self, symbol, order_type, price, qty):
                self.calls += 1
                return {"rt_cd": "0", "msg1": "ok", "output": {"ODNO": "D12345"}}

        fake_api = _FakeAPI()

        try:
            with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
                db_path = f"{tmpdir}/trades.sqlite"
                dashboard.trader.config.trade_db_path = db_path
                dashboard.AUTO_APPROVAL_STATE = MemoryCachePath()
                dashboard._get_api = lambda: fake_api
                dashboard._slack_order = lambda *args, **kwargs: None
                dashboard.trader.DRY_RUN = False
                dashboard.trader.TRADING_ENV = "demo"
                dashboard.trader.ORDER_SUBMISSION_ENABLED = True

                created = dashboard.create_approval({
                    "symbol": "005930",
                    "name": "Samsung",
                    "action": "buy",
                    "qty": 1,
                    "price": 70000,
                    "reason": "demo order",
                    "source": "test",
                })

                result = dashboard.approve_order(created["id"])
                self.assertEqual(result["status"], "executed")
                self.assertEqual(fake_api.calls, 1)

                with self.assertRaises(dashboard.HTTPException):
                    dashboard.approve_order(created["id"])
                self.assertEqual(fake_api.calls, 1)

                with sqlite3.connect(db_path) as conn:
                    conn.row_factory = sqlite3.Row
                    rows = conn.execute("SELECT * FROM trades").fetchall()

                self.assertEqual(len(rows), 1)
                self.assertEqual(rows[0]["broker_order_id"], "D12345")
                self.assertEqual(rows[0]["order_status"], "submitted")
                self.assertIn("KIS demo order submitted", rows[0]["response_msg"])
        finally:
            dashboard.trader.config.trade_db_path = original_db_path
            dashboard._get_api = original_get_api
            dashboard._slack_order = original_slack_order
            dashboard.AUTO_APPROVAL_STATE = original_auto_approval_state
            dashboard.trader.DRY_RUN = original_dry_run
            dashboard.trader.TRADING_ENV = original_trading_env
            dashboard.trader.ORDER_SUBMISSION_ENABLED = original_order_submission

    def test_order_status_sync_marks_submitted_demo_order_filled(self):
        original_db_path = dashboard.trader.config.trade_db_path
        original_dry_run = dashboard.trader.DRY_RUN

        class _FakeAPI:
            def get_trade_history(self, start_date, end_date):
                return [{
                    "odno": "D12345",
                    "tot_ccld_qty": "1",
                    "avg_prvs": "70100",
                }]

        try:
            with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
                db_path = f"{tmpdir}/trades.sqlite"
                dashboard.trader.config.trade_db_path = db_path
                dashboard.trader.DRY_RUN = False
                dashboard.trader.save_trade(
                    "005930",
                    "Samsung",
                    "buy",
                    1,
                    70000,
                    "demo order",
                    True,
                    True,
                    broker_order_id="D12345",
                    order_status="submitted",
                    filled_qty=0,
                    filled_price=0,
                )

                result = dashboard._sync_order_status_from_history(_FakeAPI(), days=1)

                self.assertEqual(result["checked_count"], 1)
                self.assertEqual(result["updated_count"], 1)
                with sqlite3.connect(db_path) as conn:
                    conn.row_factory = sqlite3.Row
                    row = conn.execute("SELECT * FROM trades").fetchone()
                self.assertEqual(row["order_status"], "filled")
                self.assertEqual(row["filled_qty"], 1)
                self.assertEqual(row["filled_price"], 70100)
        finally:
            dashboard.trader.config.trade_db_path = original_db_path
            dashboard.trader.DRY_RUN = original_dry_run

    def test_order_history_window_enforces_minimum_month_lookback(self):
        start_date, end_date = dashboard._order_history_window(1)
        start = datetime.strptime(start_date, "%Y%m%d")
        end = datetime.strptime(end_date, "%Y%m%d")

        self.assertGreaterEqual((end - start).days, 30)

    def test_order_status_sync_falls_back_to_balance_when_history_fails(self):
        original_db_path = dashboard.trader.config.trade_db_path
        original_dry_run = dashboard.trader.DRY_RUN
        original_get_balance_data = dashboard._get_balance_data

        class _FakeAPI:
            def get_trade_history(self, start_date, end_date):
                raise RuntimeError("history 500")

        try:
            with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
                db_path = f"{tmpdir}/trades.sqlite"
                dashboard.trader.config.trade_db_path = db_path
                dashboard.trader.DRY_RUN = False
                dashboard._get_balance_data = lambda api, allow_cache=False: {
                    "output1": [
                        {
                            "pdno": "005930",
                            "prdt_name": "Samsung",
                            "hldg_qty": "6",
                            "prpr": "70200",
                            "evlu_amt": "421200",
                        }
                    ],
                    "output2": [{"dnca_tot_amt": "100000", "tot_evlu_amt": "521200"}],
                }
                dashboard.trader.save_trade(
                    "005930",
                    "Samsung",
                    "buy",
                    1,
                    70000,
                    "demo order",
                    True,
                    True,
                    broker_order_id="D12345",
                    order_status="submitted",
                    filled_qty=0,
                    filled_price=0,
                    pre_order_qty=5,
                )

                result = dashboard._sync_order_status_from_history(_FakeAPI(), days=1)

                self.assertEqual(result["fallback"], "balance")
                self.assertEqual(result["history_error"], "history 500")
                self.assertEqual(result["updated_count"], 1)
                with sqlite3.connect(db_path) as conn:
                    conn.row_factory = sqlite3.Row
                    row = conn.execute("SELECT * FROM trades").fetchone()
                self.assertEqual(row["order_status"], "filled")
                self.assertEqual(row["filled_qty"], 1)
                self.assertEqual(row["filled_price"], 70200)
        finally:
            dashboard.trader.config.trade_db_path = original_db_path
            dashboard.trader.DRY_RUN = original_dry_run
            dashboard._get_balance_data = original_get_balance_data

    def test_filled_trade_history_sync_imports_lookback_rows(self):
        original_db_path = dashboard.trader.config.trade_db_path
        original_fetch_cloud_trades = dashboard.fetch_cloud_trades

        class _FakeAPI:
            def __init__(self):
                self.window = None

            def get_trade_history(self, start_date, end_date):
                self.window = (start_date, end_date)
                return [
                    {
                        "odno": "H12345",
                        "pdno": "005930",
                        "prdt_name": "Samsung",
                        "sll_buy_dvsn_cd": "02",
                        "ord_dt": "20260520",
                        "ord_tmd": "093015",
                        "tot_ccld_qty": "3",
                        "avg_prvs": "70100",
                    }
                ]

        try:
            with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
                db_path = f"{tmpdir}/trades.sqlite"
                dashboard.trader.config.trade_db_path = db_path
                dashboard.fetch_cloud_trades = lambda: []
                api = _FakeAPI()

                result = dashboard._sync_filled_trades_from_history(api, days=30)

                self.assertEqual(result["history_count"], 1)
                self.assertEqual(result["imported_count"], 1)
                self.assertNotEqual(api.window[0], api.window[1])
                with sqlite3.connect(db_path) as conn:
                    conn.row_factory = sqlite3.Row
                    row = conn.execute("SELECT * FROM trades").fetchone()
                self.assertEqual(row["ts"], "2026-05-20 09:30:15")
                self.assertEqual(row["symbol"], "005930")
                self.assertEqual(row["action"], "buy")
                self.assertEqual(row["qty"], 3)
                self.assertEqual(row["price"], 70100)
                self.assertEqual(row["order_status"], "filled")
        finally:
            dashboard.trader.config.trade_db_path = original_db_path
            dashboard.fetch_cloud_trades = original_fetch_cloud_trades

    def test_sell_all_holdings_queues_market_sell_for_each_current_holding(self):
        original_db_path = dashboard.trader.config.trade_db_path
        original_get_api = dashboard._get_api
        original_get_balance_data = dashboard._get_balance_data
        original_auto_approval = dashboard._auto_approval_enabled
        original_clear_balance_cache = dashboard._clear_balance_cache
        original_required_env_missing = dashboard._required_env_missing

        try:
            with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
                dashboard.trader.config.trade_db_path = f"{tmpdir}/trades.sqlite"
                dashboard._get_api = lambda: object()
                dashboard._get_balance_data = lambda api, allow_cache=True: {
                    "output1": [
                        {
                            "pdno": "005930",
                            "prdt_name": "Samsung",
                            "hldg_qty": "2",
                            "prpr": "70000",
                        },
                        {
                            "pdno": "000660",
                            "prdt_name": "SK Hynix",
                            "hldg_qty": "0",
                            "prpr": "120000",
                        },
                    ],
                    "output2": [{}],
                }
                dashboard._auto_approval_enabled = lambda: False
                dashboard._clear_balance_cache = lambda: None
                dashboard._required_env_missing = lambda: []

                result = dashboard.sell_all_holdings({})

                self.assertEqual(result["created_count"], 1)
                self.assertEqual(result["pending_count"], 1)
                approvals = dashboard.get_approvals()["approvals"]
                self.assertEqual(approvals[0]["symbol"], "005930")
                self.assertEqual(approvals[0]["action"], "sell")
                self.assertEqual(approvals[0]["qty"], 2)
                self.assertEqual(approvals[0]["price"], 0)
                self.assertEqual(approvals[0]["source"], "dashboard_sell_all")
        finally:
            dashboard.trader.config.trade_db_path = original_db_path
            dashboard._get_api = original_get_api
            dashboard._get_balance_data = original_get_balance_data
            dashboard._auto_approval_enabled = original_auto_approval
            dashboard._clear_balance_cache = original_clear_balance_cache
            dashboard._required_env_missing = original_required_env_missing

    def test_candidate_orders_use_scan_price_without_quote_lookup(self):
        original_max_positions = dashboard.trader.MAX_POSITIONS
        try:
            dashboard.trader.MAX_POSITIONS = 1
            orders = dashboard._build_candidate_orders_from_scan(
                [
                    {"ticker": "005930", "current_price": 70003, "score": 2, "reasons": ["test"]},
                    {"ticker": "000660", "current_price": 100000, "score": 2, "reasons": ["test"]},
                ],
                held_count=0,
                cash=1_000_000,
            )
            self.assertEqual(len(orders), 1)
            self.assertEqual(orders[0]["ticker"], "005930")
            self.assertEqual(orders[0]["limit_price"], 70000)
            self.assertLessEqual(orders[0]["estimated_cost"], 1_000_000)
        finally:
            dashboard.trader.MAX_POSITIONS = original_max_positions


if __name__ == "__main__":
    unittest.main()
