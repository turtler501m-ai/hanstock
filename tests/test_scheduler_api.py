import unittest
from unittest.mock import patch, MagicMock
from pathlib import Path
import json

from src.dashboard import get_scheduler_status, trigger_scheduler_run, _scheduler_run_state, _scheduler_running_lock

class SchedulerApiTests(unittest.TestCase):
    def setUp(self):
        # Reset global state
        with _scheduler_running_lock:
            _scheduler_run_state["is_running"] = False
            _scheduler_run_state["mode"] = None
            _scheduler_run_state["started_at"] = None
            _scheduler_run_state["completed_at"] = None
            _scheduler_run_state["result"] = None
            _scheduler_run_state["error"] = None

    @patch("src.dashboard.Path.exists", return_value=False)
    def test_get_scheduler_status_handles_missing_file_gracefully(self, mock_exists):
        status = get_scheduler_status()
        self.assertIn("config", status)
        self.assertIn("last_result", status)
        self.assertIsNone(status["last_result"])
        self.assertFalse(status["run_state"]["is_running"])

    @patch("src.dashboard.Path.exists", return_value=True)
    @patch("src.dashboard.Path.read_text", return_value='{"mode": "daily_auto", "result": {"results": []}}')
    def test_get_scheduler_status_loads_existing_result(self, mock_read, mock_exists):
        status = get_scheduler_status()
        self.assertIsNotNone(status["last_result"])
        self.assertEqual(status["last_result"]["mode"], "daily_auto")

    @patch("src.dashboard.threading.Thread")
    def test_trigger_scheduler_run_starts_background_thread(self, mock_thread):
        mock_thread_instance = MagicMock()
        mock_thread.return_value = mock_thread_instance

        response = trigger_scheduler_run(payload={"mode": "daily_auto"})
        self.assertEqual(response["status"], "started")
        self.assertEqual(response["mode"], "daily_auto")
        self.assertTrue(_scheduler_run_state["is_running"])
        mock_thread.assert_called_once()
        mock_thread_instance.start.assert_called_once()

    def test_trigger_scheduler_run_prevents_double_execution(self):
        with _scheduler_running_lock:
            _scheduler_run_state["is_running"] = True

        from fastapi import HTTPException
        with self.assertRaises(HTTPException) as ctx:
            trigger_scheduler_run(payload={"mode": "daily_auto"})
        
        self.assertEqual(ctx.exception.status_code, 409)

if __name__ == "__main__":
    unittest.main()
