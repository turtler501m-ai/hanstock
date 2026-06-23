from __future__ import annotations

import json
from pathlib import Path


def env_value_without_inline_comment(value: str) -> str:
    quote = None
    for index, char in enumerate(value):
        if char in ("'", '"') and (index == 0 or value[index - 1] != "\\"):
            quote = None if quote == char else (char if quote is None else quote)
        if char == "#" and quote is None and index > 0 and value[index - 1].isspace():
            return value[:index].strip()
    return value.strip()


def read_env_values(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip()
        value = env_value_without_inline_comment(value.strip())
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        values[key] = value
    return values


def serialize_env_value(value: str) -> str:
    if not value or any(char.isspace() for char in value) or "#" in value:
        return json.dumps(value, ensure_ascii=False)
    return value


def write_env_values(updates: dict[str, str], path: Path) -> None:
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    seen: set[str] = set()
    output: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            output.append(line)
            continue
        key = stripped.split("=", 1)[0].strip()
        if key in updates:
            value_part = line.split("=", 1)[1]
            suffix = ""
            comment_index = value_part.find(" #")
            if comment_index >= 0:
                suffix = value_part[comment_index:]
            output.append(f"{key}={serialize_env_value(updates[key])}{suffix}")
            seen.add(key)
        else:
            output.append(line)
    missing = [key for key in updates if key not in seen]
    if missing:
        if output and output[-1].strip():
            output.append("")
        output.append("# Dashboard updates")
        output.extend(f"{key}={serialize_env_value(updates[key])}" for key in missing)
    path.write_text("\n".join(output) + "\n", encoding="utf-8")


def env_bool_value(values: dict[str, str], key: str, default: bool = False) -> bool:
    raw = str(values.get(key, str(default))).strip().lower()
    return raw in {"true", "1", "yes", "on"}


def virtual_env_value(key: str, values: dict[str, str]) -> str:
    dry_run = env_bool_value(values, "DRY_RUN", True)
    trading_env = values.get("TRADING_ENV", "demo")
    enable_live = env_bool_value(values, "ENABLE_LIVE_TRADING", False)
    if key == "ORDER_SUBMISSION_ENABLED":
        return "true" if (not dry_run and (trading_env == "demo" or enable_live)) else "false"
    return ""


def expand_virtual_env_updates(updates: dict[str, str]) -> dict[str, str]:
    expanded = dict(updates)
    order_submission = expanded.pop("ORDER_SUBMISSION_ENABLED", None)

    if order_submission is not None:
        expanded["DRY_RUN"] = (
            "false"
            if env_bool_value({"value": order_submission}, "value")
            else "true"
        )

    return expanded
