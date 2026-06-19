"""DB 기반 전략 스케쥴 디스패처.

VM에서 단일 cron(예: */5 9-15 * * 1-5)이 이 모듈을 주기적으로 호출하면,
strategy_schedules 테이블에서 enabled 스케쥴을 읽어 실행 윈도우/주기 조건을
만족하는 전략만 run_scheduled_cycle로 돌린다. 전략별 cron을 따로 두지 않고
대시보드에서 등록/제어한 스케쥴 하나로 관리하기 위한 진입점이다.
"""
from __future__ import annotations

import sys
from pathlib import Path

# Add project root to sys.path to allow running as a script directly
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.db.repository import (
    is_schedule_due,
    list_strategy_schedules,
    mark_strategy_schedule_run,
)
from src.scheduler import run_scheduled_cycle
from src.utils.logger import logger


_ISOLATED_STRATEGY_IDS = {"plunge_bounce_strategy", "heikin_ashi_scalping_strategy"}


def _allowed_categories_for_strategy(strategy_id: str | None) -> set[str]:
    if strategy_id in _ISOLATED_STRATEGY_IDS:
        return {"candidate"}
    return {"position", "candidate", "ai_rebalance"}


def dispatch_due_schedules() -> list[str]:
    ran: list[str] = []
    schedules = list_strategy_schedules(enabled_only=True)
    if not schedules:
        logger.info("[dispatch] no enabled strategy schedules")
        return ran

    for sched in schedules:
        strategy_id = sched.get("strategy_id")
        if not is_schedule_due(sched):
            continue
        mode = str(sched.get("mode") or "execute")
        auto_approve = bool(sched.get("auto_approve"))
        try:
            logger.info(
                f"[dispatch] running {strategy_id} (mode={mode}, auto_approve={auto_approve})"
            )
            run_scheduled_cycle(
                mode,
                auto_approve=auto_approve,
                force_strategy_id=strategy_id,
                allowed_categories=_allowed_categories_for_strategy(strategy_id),
            )
            mark_strategy_schedule_run(strategy_id)
            ran.append(strategy_id)
            logger.info(f"[dispatch] done {strategy_id}")
        except Exception as exc:  # noqa: BLE001
            logger.error(f"[dispatch] {strategy_id} failed: {exc}")
    return ran


def main() -> int:
    ran = dispatch_due_schedules()
    print(f"[dispatch] ran: {ran}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
