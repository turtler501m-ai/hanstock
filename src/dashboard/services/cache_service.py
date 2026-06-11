from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

from src.db.scheduler_repository import (
    delete_account_snapshot,
    load_account_snapshot,
    save_account_snapshot,
)
from src.utils.logger import logger


class DashboardCacheService:
    def __init__(
        self,
        balance_cache_path: Path,
        *,
        account_key_fn: Callable[[], str],
        trading_env_fn: Callable[[], str],
        captured_at_fn: Callable[[], str],
        derived_kinds: tuple[str, ...],
    ) -> None:
        self.balance_cache_path = balance_cache_path
        self.account_key_fn = account_key_fn
        self.trading_env_fn = trading_env_fn
        self.captured_at_fn = captured_at_fn
        self.derived_kinds = derived_kinds

    def save_balance(self, balance_data: dict) -> None:
        envelope = {
            "cached_at": self.captured_at_fn(),
            "trading_env": self.trading_env_fn(),
            "account_key": self.account_key_fn(),
            "data": balance_data,
        }
        self.balance_cache_path.parent.mkdir(parents=True, exist_ok=True)
        self.balance_cache_path.write_text(
            json.dumps(envelope, ensure_ascii=False),
            encoding="utf-8",
        )
        try:
            save_account_snapshot(
                envelope["account_key"],
                envelope["trading_env"],
                "balance",
                envelope,
                envelope["cached_at"],
            )
        except (OSError, ValueError, TypeError) as exc:
            logger.warning(f"Failed to persist balance snapshot: {exc}")

    def clear_balance(self) -> None:
        try:
            self.balance_cache_path.unlink(missing_ok=True)
        except OSError as exc:
            logger.warning(f"Failed to remove balance cache: {exc}")
        for kind in self.derived_kinds:
            try:
                delete_account_snapshot(
                    self.account_key_fn(),
                    self.trading_env_fn(),
                    kind,
                )
            except (OSError, ValueError, TypeError) as exc:
                logger.warning(f"Failed to clear {kind} snapshot: {exc}")

    def balance_envelope_to_data(self, envelope) -> dict | None:
        if not isinstance(envelope, dict):
            return None
        if envelope.get("trading_env") != self.trading_env_fn():
            return None
        if envelope.get("account_key") != self.account_key_fn():
            return None
        data = envelope.get("data")
        if not isinstance(data, dict):
            return None
        result = dict(data)
        result["_cache"] = {
            "stale": True,
            "cached_at": envelope.get("cached_at", ""),
        }
        return result

    def load_balance(self) -> dict | None:
        if self.balance_cache_path.exists():
            try:
                envelope = json.loads(
                    self.balance_cache_path.read_text(encoding="utf-8")
                )
            except (OSError, UnicodeError, json.JSONDecodeError) as exc:
                logger.warning(f"Failed to read balance cache: {exc}")
            else:
                data = self.balance_envelope_to_data(envelope)
                if data is not None:
                    return data

        try:
            snapshot = load_account_snapshot(
                self.account_key_fn(),
                self.trading_env_fn(),
                "balance",
            )
        except (OSError, ValueError, TypeError) as exc:
            logger.warning(f"Failed to load balance snapshot: {exc}")
            return None
        if snapshot is None:
            return None
        return self.balance_envelope_to_data(snapshot["payload"])
