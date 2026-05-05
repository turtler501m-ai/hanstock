from __future__ import annotations

from datetime import datetime
import re
from uuid import uuid5, NAMESPACE_URL

from .models import Direction, FuturesSignal


_DIRECTION_ALIASES: dict[str, Direction] = {
    "LONG": "long",
    "BUY": "long",
    "BULL": "long",
    "매수": "long",
    "롱": "long",
    "SHORT": "short",
    "SELL": "short",
    "BEAR": "short",
    "매도": "short",
    "숏": "short",
}

_MONTH_ALIASES = {
    "JAN": "F",
    "FEB": "G",
    "MAR": "H",
    "APR": "J",
    "MAY": "K",
    "JUN": "M",
    "JUL": "N",
    "AUG": "Q",
    "SEP": "U",
    "SEPT": "U",
    "OCT": "V",
    "NOV": "X",
    "DEC": "Z",
}

_NUMBER = r"([0-9]+(?:\.[0-9]+)?)"
_SYMBOL_RE = re.compile(
    r"(?<![A-Z0-9])/?([A-Z]{1,6})(?:[\s\-/]*([FGHJKMNQUVXZ])\s*(\d{1,4})|[\s\-/]+(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|SEPT|OCT|NOV|DEC)\s*(\d{2,4}))?(?![A-Z0-9])",
    re.IGNORECASE,
)
_DIRECTION_RE = re.compile(r"\b(LONG|SHORT|BUY|SELL|BULL|BEAR)\b|매수|매도|롱|숏", re.IGNORECASE)
_ENTRY_RE = re.compile(rf"(?:\b(?:ENTRY|ENTER|ENT|AT|LIMIT)\b|진입가|진입|@)\s*[:=\-]?\s*{_NUMBER}", re.IGNORECASE)
_MARKET_ENTRY_RE = re.compile(r"(?:진입가|진입|ENTRY|ENTER|ENT)\s*[:=\-]?\s*시장가|\bMARKET\b", re.IGNORECASE)
_STOP_RE = re.compile(rf"\b(?:SL|STOP|STOP\s*LOSS|S/L)\s*[:=\-]?\s*{_NUMBER}|손절\s*[:=\-]?\s*{_NUMBER}", re.IGNORECASE)
_TP_RE = re.compile(
    rf"\b(?:TP\s*\d*|TARGET|TAKE\s*PROFIT)\s*[:=\-]?\s*{_NUMBER}"
    rf"|(?:익절|목표가|청산|청산가|수익청산|부분청산|전량청산|\d+\s*차\s*청산)\s*[:=\-]?\s*{_NUMBER}",
    re.IGNORECASE,
)

_NOISE_WORDS = {
    "LONG",
    "SHORT",
    "BUY",
    "SELL",
    "BULL",
    "BEAR",
    "ENTRY",
    "ENTER",
    "LIMIT",
    "STOP",
    "LOSS",
    "TARGET",
    "TAKE",
    "PROFIT",
    "TP",
    "SL",
}


class FuturesSignalParseError(ValueError):
    pass


def normalize_direction(value: str) -> Direction:
    key = value.strip().upper()
    try:
        return _DIRECTION_ALIASES[key]
    except KeyError as exc:
        raise FuturesSignalParseError(f"Unsupported futures direction: {value}") from exc


def normalize_symbol(value: str) -> str:
    compact = re.sub(r"[^A-Za-z0-9]", "", value).upper()
    if not compact:
        raise FuturesSignalParseError("Missing futures symbol")

    month_name = re.search(r"(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|SEPT|OCT|NOV|DEC)(\d{2,4})$", compact)
    if month_name:
        root = compact[: month_name.start()]
        year = _normalize_year(month_name.group(2))
        return f"{root}{_MONTH_ALIASES[month_name.group(1)]}{year}"

    match = re.match(r"^([A-Z]{1,6})([FGHJKMNQUVXZ])(\d{1,4})$", compact)
    if match:
        return f"{match.group(1)}{match.group(2)}{_normalize_year(match.group(3))}"
    return compact


def parse_futures_signal(
    text: str,
    *,
    source: str = "telegram",
    source_message_id: str | None = None,
    received_at: datetime | None = None,
) -> FuturesSignal:
    raw_text = text.strip()
    if not raw_text:
        raise FuturesSignalParseError("Cannot parse an empty futures signal")

    direction_match = _DIRECTION_RE.search(raw_text)
    if not direction_match:
        raise FuturesSignalParseError("Missing futures direction")
    direction = normalize_direction(direction_match.group(1) or direction_match.group(0))

    symbol = _find_symbol(raw_text)
    entry = _find_optional_price(_ENTRY_RE, raw_text)
    stop_loss = _find_optional_price(_STOP_RE, raw_text)
    take_profits = tuple(_match_price(match) for match in _TP_RE.finditer(raw_text))
    market_entry = _MARKET_ENTRY_RE.search(raw_text) is not None or ("시장가" in raw_text and "진입" in raw_text)

    needs_review = False
    if entry is None and market_entry:
        entry = 0.0
        needs_review = True
    if stop_loss is None and market_entry:
        stop_loss = 0.0
        needs_review = True

    if entry is None:
        raise FuturesSignalParseError("Missing entry")
    if stop_loss is None:
        raise FuturesSignalParseError("Missing stop loss")
    if not take_profits and not market_entry:
        raise FuturesSignalParseError("Missing take profit")

    if not needs_review:
        _validate_price_shape(direction, entry, stop_loss, take_profits)
    message_id = source_message_id or str(uuid5(NAMESPACE_URL, f"{source}:{raw_text}"))
    return FuturesSignal(
        id=f"{source}:{message_id}",
        source=source,
        source_message_id=message_id,
        received_at=received_at,
        raw_text=raw_text,
        symbol=symbol,
        direction=direction,
        entry=entry,
        stop_loss=stop_loss,
        take_profits=take_profits,
        status="needs_review" if needs_review else "parsed",
    )


def _find_symbol(text: str) -> str:
    for match in _SYMBOL_RE.finditer(text):
        candidate = match.group(0).strip()
        root = match.group(1).upper()
        if root not in _NOISE_WORDS:
            return normalize_symbol(candidate)
    raise FuturesSignalParseError("Missing futures symbol")


def _find_required_price(pattern: re.Pattern[str], text: str, label: str) -> float:
    match = pattern.search(text)
    if not match:
        raise FuturesSignalParseError(f"Missing {label}")
    return _match_price(match)


def _find_optional_price(pattern: re.Pattern[str], text: str) -> float | None:
    match = pattern.search(text)
    if not match:
        return None
    return _match_price(match)


def _match_price(match: re.Match[str]) -> float:
    for group in match.groups():
        if group is not None:
            return float(group)
    raise FuturesSignalParseError("Missing price")


def _normalize_year(value: str) -> str:
    if len(value) == 4:
        return value[-2:]
    return value.zfill(2)


def _validate_price_shape(direction: Direction, entry: float, stop_loss: float, take_profits: tuple[float, ...]) -> None:
    if direction == "long":
        if stop_loss >= entry:
            raise FuturesSignalParseError("Long stop loss must be below entry")
        if any(target <= entry for target in take_profits):
            raise FuturesSignalParseError("Long take profits must be above entry")
    else:
        if stop_loss <= entry:
            raise FuturesSignalParseError("Short stop loss must be above entry")
        if any(target >= entry for target in take_profits):
            raise FuturesSignalParseError("Short take profits must be below entry")
