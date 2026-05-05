"""Poll a channel for new messages, extract trading signals, store to DB.

Usage: poll.py <channel_key> <id_or_username> <label>

For each new message (id > last_message_id):
  - Group recent context (last 10 messages from same channel)
  - Ask LLM to detect & extract signals
  - Store extracted signals to DB
  - Update poll_state.last_message_id
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from . import db as signals_db
from telethon import TelegramClient
from telethon.tl.types import PeerChannel

load_dotenv()
KST = timezone(timedelta(hours=9))

# Use VM's session file and credentials
VM_ROOT = Path("/home/turtler800/scripts/channel-monitor")
API_ID = int(os.environ.get("TELEGRAM_API_ID", os.environ.get("TG_API_ID", "38298339")))
API_HASH = os.environ.get("TELEGRAM_API_HASH", os.environ.get("TG_API_HASH", "17ccdf1a06ce938b600b6beaf4c43787"))

EXTRACT_PROMPT = """다음은 텔레그램 해외선물 시그널 채널의 최근 메시지들입니다.
한국 시그널 채팅 특성상 한 시그널이 여러 메시지로 쪼개져 올라오기도 합니다.

작업: **새 메시지 (NEW로 표시) 중에서 매매 시그널만** 추출해주세요.

매매 시그널 = 다음 두 가지 유형 모두 추출:
(1) 진입 신호: "진입", "매수", "롱", "숏", "매도", "들어갑니다", "대기", "추가진입", "재진입"
(2) 청산 신호: "익절", "청산", "손절", "반매도", "정리", "종결", "마감", "나감", "종료"

일반 채팅, 안부, 뉴스, 이벤트 안내, 가입/입금/정회원 유도는 제외.

重要:
- NEW 메시지 하나에 종목/방향이 모두 없더라도, 직전 CTX에서 같은 흐름의 종목/방향을 명확히 보완할 수 있으면 추출하세요.
- 청산 신호: "익절", "청산", "손절", "반매도" 키워드가 있으면 exit로 분류
- 진입/청산 모두 keyword 있으면両方 추출
- 같은 의미의 반복 메시지가 여러 개 있으면 가장 마지막 NEW message_id 하나만 추출하세요.

출력 형식 (JSON 배열, 시그널 없으면 빈 배열 []):
[
  {{
    "message_id": 123,
    "symbol": "나스닥",
    "direction": "long",
    "entry_price": 18500.0,
    "stop_loss": 18450.0,
    "target_price": 18600.0,
    "confidence": 0.9,
    "notes": "정확한 진입가 명시"
  }}
]

필드:
- direction: "long"(진입), "short"(진입), 또는 "exit"(청산/익절/손절)
- entry_price, stop_loss, target_price: 숫자 또는 null
- confidence: 0.0-1.0 (시그널 명확도)
- notes: 한 문장

반드시 **유효한 JSON 배열만** 출력. 분석/설명/마크다운 절대 금지. 시작은 `[` 끝은 `]`.

메시지 (CTX=과거 컨텍스트, NEW=새 메시지):
{messages}
"""


def format_messages_for_prompt(new_msgs: list[dict], context_msgs: list[dict]) -> str:
    lines = []
    for m in context_msgs:
        text = (m.get("raw_text", "") or "").replace("\n", " ")[:300]
        lines.append(f"CTX | id={m.get('telegram_message_id')} | {m.get('received_at', '')[:5]} | {text}")
    for m in new_msgs:
        text = (m.get("raw_text", "") or "").replace("\n", " ")[:300]
        lines.append(f"NEW | id={m.get('telegram_message_id')} | {m.get('received_at', '')[:5]} | {text}")
    return "\n".join(lines)


def extract_signals_via_llm(prompt: str) -> list[dict]:
    """Extract signals using regex fallback (no external LLM required)."""
    return _extract_signals_fallback(prompt)


def _extract_signals_fallback(prompt: str) -> list[dict]:
    """Simple regex-based signal extraction as fallback."""
    signals = []
    lines = prompt.split("\n")

    symbol_map = {
        "나스닥": "나스닥", "NQ": "나스닥", "NASDAQ": "나스닥",
        "MNQ": "마이크로나스닥", "마이크로나스닥": "마이크로나스닥",
        "골드": "골드", "GC": "골드", " GOLD ": "골드",
        "크루드오일": "크루드오일", "CL": "크루드오일", "WTI": "크루드오일", "유일": "크루드오일",
        "항셍": "항셍", "HSI": "항셍", "항셍이": "항셍",
    }

    entry_keywords = ["진입", "진행", "대기", "포지션", "들어갑니다", "들어가요", "매수", "매도", "롱", "숏"]
    exit_keywords = ["익절", "청산", "손절", "반매도", "정리", "종결", "마감", "나감", "종료"]

    last_symbol = None
    last_entry_direction = None
    last_exit_message_id = None

    for line in lines:
        if not line.startswith("CTX") and not line.startswith("NEW"):
            continue
        
        msg_match = re.search(r"id=(\d+)", line)
        if not msg_match:
            continue
        msg_id = int(msg_match.group(1))
        text = line

        for kw, sym in symbol_map.items():
            if kw.lower() in text.lower() or kw in text:
                last_symbol = sym
                break

        for kw in ["매수", "롱", "BUY", "long"]:
            if kw in text:
                last_entry_direction = "long"
                break

        for kw in ["매도", "숏", "SELL", "short"]:
            if kw in text:
                last_entry_direction = "short"
                break

        if any(kw in text for kw in exit_keywords):
            if last_symbol:
                signals.append({
                    "message_id": msg_id,
                    "symbol": last_symbol,
                    "direction": "exit",
                    "entry_price": None,
                    "stop_loss": None,
                    "target_price": None,
                    "confidence": 0.7,
                    "notes": "regex exit"
                })

    if last_entry_direction and any(kw in line for kw in entry_keywords for line in lines if line.startswith("CTX") or line.startswith("NEW")):
        msg_id = None
        for line in lines:
            if line.startswith("NEW"):
                m = re.search(r"id=(\d+)", line)
                if m:
                    msg_id = int(m.group(1))
        if msg_id and last_symbol:
            signals.append({
                "message_id": msg_id,
                "symbol": last_symbol,
                "direction": last_entry_direction,
                "entry_price": None,
                "stop_loss": None,
                "target_price": None,
                "confidence": 0.6 if last_symbol else 0.5,
                "notes": "regex entry"
            })
    
    return signals


def normalize_direction(value: str) -> str:
    if value in ("long", "short", "exit"):
        return value
    if value in ("롱", "매수", "buy"):
        return "long"
    if value in ("숏", "매도", "sell"):
        return "short"
    if value in ("청산", "익절", "손절", "반매도", "정리", "종결", "close", "exit"):
        return "exit"
    return value


def as_float_or_none(value) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        cleaned = re.sub(r"[^0-9.\-]", "", value)
        if not cleaned:
            return None
        try:
            return float(cleaned)
        except ValueError:
            return None
    return None


def normalize_signals(signals: list[dict]) -> list[dict]:
    normalized = []
    seen = set()
    for sig in signals:
        if not isinstance(sig, dict):
            continue
        try:
            mid = int(sig.get("message_id"))
        except (TypeError, ValueError):
            continue
        symbol = str(sig.get("symbol") or "").strip()
        direction = normalize_direction(str(sig.get("direction")))
        if not symbol or direction not in ("long", "short", "exit"):
            continue
        try:
            confidence = float(sig.get("confidence") or 0)
        except (TypeError, ValueError):
            confidence = 0.0
        normalized_sig = {
            "message_id": mid,
            "symbol": symbol,
            "direction": direction,
            "entry_price": as_float_or_none(sig.get("entry_price")),
            "stop_loss": as_float_or_none(sig.get("stop_loss")),
            "target_price": as_float_or_none(sig.get("target_price")),
            "confidence": max(0.0, min(confidence, 1.0)),
            "notes": str(sig.get("notes") or "").strip()[:300],
        }
        key = (
            normalized_sig["symbol"].lower(),
            normalized_sig["direction"],
            normalized_sig["entry_price"],
            normalized_sig["stop_loss"],
            normalized_sig["target_price"],
        )
        if key in seen:
            normalized = [s for s in normalized if (
                s["symbol"].lower(),
                s["direction"],
                s["entry_price"],
                s["stop_loss"],
                s["target_price"],
            ) != key]
        seen.add(key)
        normalized.append(normalized_sig)
    return normalized


def store_signals(channel_key: str, new_msgs: list[dict], signals: list[dict]) -> list[dict]:
    msg_by_id = {int(m.get("telegram_message_id", 0)): m for m in new_msgs}
    inserted_signals = []
    for sig in signals:
        mid = sig.get("message_id")
        if mid not in msg_by_id:
            continue
        m = msg_by_id[mid]
        message_date = m.get("received_at", "")
        raw_text = m.get("raw_text", "")

        inserted = signals_db.insert_signal(
            channel_key=channel_key,
            message_id=mid,
            message_date=message_date,
            raw_text=raw_text,
            symbol=sig.get("symbol"),
            direction=sig.get("direction"),
            entry_price=sig.get("entry_price"),
            stop_loss=sig.get("stop_loss"),
            target_price=sig.get("target_price"),
            confidence=sig.get("confidence"),
            notes=sig.get("notes"),
        )
        if inserted:
            inserted_signals.append({**sig, "channel_key": channel_key, "message_date": message_date, "raw_text": raw_text})
    return inserted_signals


def load_channels() -> list[dict[str, str]]:
    """Load channels from channels.json."""
    channels_path = Path("channels.json")
    if not channels_path.exists():
        channels_path = Path(__file__).parent.parent / "channels.json"
    if not channels_path.exists():
        return []
    with open(channels_path) as f:
        data = json.load(f)
    return [c for c in data if c.get("signal_tracking")]


async def fetch_new_and_context(client, target, last_message_id: int, context_size: int = 10):
    """Fetch new messages and context messages from a channel."""
    try:
        entity = await client.get_entity(PeerChannel(int(target)))
    except ValueError:
        entity = await client.get_entity(target.lstrip("@"))

    new_msgs = []
    context_msgs = []
    async for m in client.iter_messages(entity, limit=500):
        if m.id > last_message_id:
            new_msgs.append(m)
        else:
            if len(context_msgs) < context_size:
                context_msgs.append(m)
            else:
                break
    new_msgs.reverse()
    context_msgs.reverse()
    return entity, new_msgs, context_msgs


async def poll_channel(channel_key: str, target: str, label: str):
    """Poll a single channel for new messages."""
    signals_db.init_db()

    state = signals_db.get_channel_state(channel_key)
    last_id = state["last_message_id"] if state else 0

    # Use VM's session file
    session_file = VM_ROOT / "user.session"
    if not session_file.exists():
        print(f"[{channel_key}] session file not found: {session_file}")
        return

    client = TelegramClient(str(session_file), API_ID, API_HASH)
    await client.connect()
    try:
        if not await client.is_user_authorized():
            print(f"[{channel_key}] not authorized")
            return

        entity, new_msgs, context_msgs = await fetch_new_and_context(client, target, last_id)

        if not new_msgs:
            print(f"[{channel_key}] no new messages (last_id={last_id})")
            return

        if last_id == 0 and os.environ.get("POLLING_BACKFILL") != "1":
            latest_id = max(m.id for m in new_msgs)
            signals_db.update_channel_state(channel_key, latest_id)
            print(f"[{channel_key}] first run: set last_id={latest_id} (no extraction)")
            return

        print(f"[{channel_key}] {len(new_msgs)} new messages, {len(context_msgs)} ctx")

        # Convert messages to dict format for prompt
        new_dicts = [{
            "telegram_message_id": str(m.id),
            "received_at": m.date.astimezone(KST).isoformat(),
            "raw_text": m.message or "",
        } for m in new_msgs]
        ctx_dicts = [{
            "telegram_message_id": str(m.id),
            "received_at": m.date.astimezone(KST).isoformat(),
            "raw_text": m.message or "",
        } for m in context_msgs]

        prompt = EXTRACT_PROMPT.format(messages=format_messages_for_prompt(new_dicts, ctx_dicts))
        signals = normalize_signals(extract_signals_via_llm(prompt))
        print(f"[{channel_key}] extracted {len(signals)} signal(s)")

        # Store signals
        msg_by_id = {m.id: m for m in new_msgs}
        inserted_signals = []
        for sig in signals:
            mid = sig.get("message_id")
            if mid not in msg_by_id:
                continue
            m = msg_by_id[mid]
            message_date = m.date.astimezone(KST).isoformat()
            raw_text = m.message or ""

            inserted = signals_db.insert_signal(
                channel_key=channel_key,
                message_id=mid,
                message_date=message_date,
                raw_text=raw_text,
                symbol=sig.get("symbol"),
                direction=sig.get("direction"),
                entry_price=sig.get("entry_price"),
                stop_loss=sig.get("stop_loss"),
                target_price=sig.get("target_price"),
                confidence=sig.get("confidence"),
                notes=sig.get("notes"),
            )
            if inserted:
                inserted_signals.append({**sig, "channel_key": channel_key, "message_date": message_date, "raw_text": raw_text})

        latest_id = max(m.id for m in new_msgs)
        signals_db.update_channel_state(channel_key, latest_id)
        print(f"[{channel_key}] inserted {len(inserted_signals)}, last_id -> {latest_id}")
    finally:
        await client.disconnect()


async def main():
    signals_db.init_db()

    channels = load_channels()
    if not channels:
        print("No channels with signal_tracking=true found")
        sys.exit(1)

    for ch in channels:
        key = ch.get("key", "")
        target = ch.get("id_or_username", "")
        label = ch.get("label", "")
        if not key or not target:
            continue
        try:
            await poll_channel(key, str(target), label)
        except Exception as e:
            print(f"ERROR [{key}]: {e}")


if __name__ == "__main__":
    asyncio.run(main())