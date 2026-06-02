from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Callable


KST = timezone(timedelta(hours=9))


def format_kst_timestamp(value: datetime | None = None, fmt: str = "%Y-%m-%d %H:%M KST") -> str:
    current = value or datetime.now(KST)
    if current.tzinfo is None:
        current = current.replace(tzinfo=KST)
    else:
        current = current.astimezone(KST)
    return current.strftime(fmt)


def build_slack_payload(
    text: str = "",
    blocks: list[dict[str, Any]] | None = None,
    color: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    if text:
        payload["text"] = text
    if color:
        attachment: dict[str, Any] = {"color": color}
        if blocks:
            attachment["blocks"] = blocks
        if text:
            attachment["fallback"] = text
        payload["attachments"] = [attachment]
        return payload
    if blocks:
        payload["blocks"] = blocks
    return payload


def post_slack_payload(
    webhook_url: str,
    payload: dict[str, Any],
    session: Any,
    timeout: int = 10,
    log_fn: Callable[[str], None] | None = None,
) -> bool:
    if not webhook_url:
        return False
    try:
        response = session.post(webhook_url, json=payload, timeout=timeout)
        if response.status_code != 200:
            if log_fn:
                log_fn(f"[WARN] Slack send failed HTTP {response.status_code}: {response.text[:100]}")
            return False
        return True
    except Exception as exc:  # pragma: no cover - exercised via tests with a fake session
        if log_fn:
            log_fn(f"[WARN] Slack exception: {exc}")
        return False


def send_slack_message(
    webhook_url: str,
    session: Any,
    text: str = "",
    blocks: list[dict[str, Any]] | None = None,
    color: str | None = None,
    timeout: int = 10,
    log_fn: Callable[[str], None] | None = None,
) -> bool:
    payload = build_slack_payload(text=text, blocks=blocks, color=color)
    return post_slack_payload(
        webhook_url=webhook_url,
        payload=payload,
        session=session,
        timeout=timeout,
        log_fn=log_fn,
    )


def build_session_start_payload(
    cash: int,
    total: int,
    stock_count: int,
    *,
    now: datetime | None = None,
    mode: str,
    trading_env: str,
) -> dict[str, Any]:
    ts = format_kst_timestamp(now)
    return build_slack_payload(
        text=f"세븐 스플릿 자동매매 시작 - {ts}",
        blocks=[
            {"type": "header", "text": {"type": "plain_text", "text": "세븐 스플릿 자동매매 시작"}},
            {"type": "section", "fields": [
                {"type": "mrkdwn", "text": f"*시간*\n{ts}"},
                {"type": "mrkdwn", "text": f"*실행 모드*\n{mode}"},
                {"type": "mrkdwn", "text": f"*API 환경*\n{trading_env}"},
                {"type": "mrkdwn", "text": f"*예수금*\n{cash:,}원"},
                {"type": "mrkdwn", "text": f"*총 평가금액*\n{total:,}원"},
                {"type": "mrkdwn", "text": f"*보유 종목*\n{stock_count}개"},
            ]},
        ],
        color="#2196F3",
    )


def build_order_payload(
    name: str,
    symbol: str,
    action: str,
    qty: float,
    price: float,
    reason: str,
    ok: bool,
    indicators: dict[str, Any] | None = None,
) -> dict[str, Any]:
    details = indicators or {}
    action_label = "매수" if action == "buy" else "매도"
    status = "성공" if ok else "실패"
    
    # US stock symbols typically have letters, while Korean stocks are numeric digits
    is_us = not symbol.isdigit()
    
    if is_us:
        price_str = f"${price:,.2f}" if price else "시장가"
        amount_str = f"${qty * price:,.2f}" if price else "-"
        qty_str = f"{qty}주" if float(qty).is_integer() else f"{qty:.4f}주"
    else:
        price_str = f"{int(price):,}원" if price else "시장가"
        amount_str = f"{int(qty * price):,}원" if price else "-"
        qty_str = f"{int(qty)}주" if float(qty).is_integer() else f"{qty}주"

    rsi_value = details.get("rsi", "-")
    rsi_str = f"{rsi_value:.1f}" if isinstance(rsi_value, float) else str(rsi_value)
    return build_slack_payload(
        text=f"{action_label} {name} {qty_str} {status}",
        blocks=[
            {"type": "section", "text": {"type": "mrkdwn", "text": f"*{action_label}* {name} (`{symbol}`) {status}"}},
            {"type": "section", "fields": [
                {"type": "mrkdwn", "text": f"*수량*\n{qty_str}"},
                {"type": "mrkdwn", "text": f"*가격*\n{price_str}"},
                {"type": "mrkdwn", "text": f"*금액*\n{amount_str}"},
                {"type": "mrkdwn", "text": f"*RSI*\n{rsi_str}"},
                {"type": "mrkdwn", "text": f"*SMA20/60*\n{details.get('sma20', 0):.0f} / {details.get('sma60', 0):.0f}"},
                {"type": "mrkdwn", "text": f"*수익률*\n{details.get('rt', 0):+.2f}%"},
            ]},
            {"type": "context", "elements": [{"type": "mrkdwn", "text": f"사유: {reason}"}]},
        ],
        color="#36a64f" if ok else "#e74c3c",
    )


def build_candidates_payload(candidates: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not candidates:
        return None
    
    blocks = [{"type": "header", "text": {"type": "plain_text", "text": "매수 후보 종목"}}]
    current_chunk = []
    current_length = 0
    
    for item in candidates:
        ticker = item["ticker"]
        label = item.get("name") or ticker
        line = f"*{label}* (`{ticker}`) {item['current_price']:,.0f}원 | 점수 {item['score']} | {', '.join(item['reasons'])}"
        line_len = len(line) + 1
        
        if current_length + line_len > 2800:
            blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": "\n".join(current_chunk)}})
            current_chunk = [line]
            current_length = line_len
        else:
            current_chunk.append(line)
            current_length += line_len
            
    if current_chunk:
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": "\n".join(current_chunk)}})
        
    return build_slack_payload(
        text=f"신규 매수 후보 {len(candidates)}종목",
        blocks=blocks,
        color="#9C27B0",
    )


def build_session_end_payload(
    results: list[dict[str, Any]],
    cash: int,
    total: int,
    pnl: int,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    ts = format_kst_timestamp(now)
    if not results:
        return build_slack_payload(
            text=f"세븐 스플릿 자동매매 종료 - {ts}: 주문 없음",
            color="#9E9E9E",
        )

    executed = [item for item in results if item.get("decision", "execute") == "execute"]
    queued_count = sum(1 for item in results if item.get("decision") == "queue")
    buy_count = sum(1 for item in executed if item["action"] == "buy" and item["ok"])
    sell_count = sum(1 for item in executed if item["action"] == "sell" and item["ok"])
    fail_count = sum(1 for item in executed if not item["ok"])
    
    blocks = [
        {"type": "header", "text": {"type": "plain_text", "text": "세븐 스플릿 자동매매 종료"}},
        {"type": "section", "fields": [
            {"type": "mrkdwn", "text": f"*시간*\n{ts}"},
            {"type": "mrkdwn", "text": f"*총 평가금액*\n{total:,}원"},
            {"type": "mrkdwn", "text": f"*예수금*\n{cash:,}원"},
            {"type": "mrkdwn", "text": f"*당일 손익*\n{pnl:+,}원"},
            {"type": "mrkdwn", "text": f"*매수 성공*\n{buy_count}건"},
            {"type": "mrkdwn", "text": f"*매도 성공*\n{sell_count}건"},
            {"type": "mrkdwn", "text": f"*승인대기*\n{queued_count}건"},
        ]}
    ]

    current_chunk = ["*주문 내역*"]
    current_length = len(current_chunk[0])
    
    for item in results:
        if item.get("decision") == "queue":
            prefix = "승인대기"
        else:
            prefix = "매수" if item["action"] == "buy" else "매도"
        line = f"{prefix} {item['name']} {item['qty']}주 - {item['reason']}"
        line_len = len(line) + 1
        
        if current_length + line_len > 2800:
            blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": "\n".join(current_chunk)}})
            current_chunk = [line]
            current_length = line_len
        else:
            current_chunk.append(line)
            current_length += line_len
            
    if current_chunk:
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": "\n".join(current_chunk)}})

    blocks.append({"type": "context", "elements": [{"type": "mrkdwn", "text": f"실패 건수: {fail_count}건"}]})

    return build_slack_payload(
        text=f"세븐 스플릿 자동매매 종료 - {ts}",
        blocks=blocks,
        color="#36a64f" if pnl >= 0 else "#e74c3c",
    )


def build_error_payload(message: str) -> dict[str, Any]:
    return build_slack_payload(text=f"세븐 스플릿 오류: {message}", color="#e74c3c")

