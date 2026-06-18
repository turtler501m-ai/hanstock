# -*- coding: utf-8 -*-
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.strategy.narrative_momentum import (  # noqa: E402
    STRATEGY_ID,
    NarrativeMomentumStrategy,
    load_json_file,
    save_json_file,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run narrative momentum scan.")
    parser.add_argument("--history", default=str(ROOT / ".runtime" / "narrative_history.json"))
    parser.add_argument("--theme-map", default=str(ROOT / "config" / "theme_map.json"))
    parser.add_argument("--output", default=str(ROOT / ".runtime" / "narrative_momentum_latest.json"))
    parser.add_argument("--today", default=None)
    parser.add_argument("--limit", type=int, default=20)
    args = parser.parse_args()

    history = load_json_file(args.history, [])
    theme_map = load_json_file(args.theme_map, {})
    if not isinstance(history, list):
        raise SystemExit("narrative history must be a list")
    if not isinstance(theme_map, dict):
        raise SystemExit("theme map must be an object")

    strategy = NarrativeMomentumStrategy()
    status = strategy.status(history, theme_map, today_str=args.today)
    signals = strategy.calculate_signals(history, theme_map, today_str=args.today)
    payload = {
        "strategy": STRATEGY_ID,
        "status": status,
        "signals": signals,
        "total_scanned": len(signals),
    }
    save_json_file(args.output, payload)
    print(json.dumps({"status": status, "total_scanned": len(signals), "top": signals[: args.limit]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
