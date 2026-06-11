from __future__ import annotations

import math
from typing import Any

import yfinance as yf

from src.mistock.config import config
from src.strategy.indicators import calc_bollinger, calc_macd, calc_rsi, calc_sma

NASDAQ_UNIVERSE = list(config.universe_list)

NASDAQ_NAMES = {
    "AAPL": "Apple",
    "MSFT": "Microsoft",
    "NVDA": "NVIDIA",
    "AMZN": "Amazon",
    "META": "Meta Platforms",
    "GOOGL": "Alphabet Class A",
    "GOOG": "Alphabet Class C",
    "TSLA": "Tesla",
    "AVGO": "Broadcom",
    "COST": "Costco",
    "NFLX": "Netflix",
    "AMD": "Advanced Micro Devices",
    "PEP": "PepsiCo",
    "ADBE": "Adobe",
    "CSCO": "Cisco",
    "TMUS": "T-Mobile US",
    "INTU": "Intuit",
    "QCOM": "Qualcomm",
    "AMAT": "Applied Materials",
    "TXN": "Texas Instruments",
}


def normalize_symbol(symbol: str) -> str:
    return "".join(ch for ch in str(symbol or "").upper().strip() if ch.isalnum() or ch in {".", "-"}).replace("-", ".")


def symbol_name(symbol: str) -> str:
    symbol = normalize_symbol(symbol)
    return NASDAQ_NAMES.get(symbol, symbol)


def strategy_profile(prices: list[float], highs: list[float] | None = None, volumes: list[float] | None = None) -> dict[str, Any]:
    highs = highs or prices
    volumes = volumes or []
    current = prices[-1] if prices else 0.0
    prev = prices[-2] if len(prices) >= 2 else current
    rsi14 = calc_rsi(prices, 14)
    rsi2 = calc_rsi(prices, 2)
    sma20 = calc_sma(prices, 20)
    sma60 = calc_sma(prices, 60)
    sma120 = calc_sma(prices, 120)
    bb_lo, _bb_mid, _bb_hi = calc_bollinger(prices, 20)
    macd = calc_macd(prices)
    score = 0
    reasons: list[str] = []

    if len(prices) >= 16:
        prev_rsi = calc_rsi(prices[:-1], 14)
        if prev_rsi < config.rsi_buy <= rsi14:
            score += 2
            reasons.append(f"RSI recovery {prev_rsi:.0f}->{rsi14:.0f}")
        elif 35 < rsi14 < 55:
            score += 1
            reasons.append(f"NASDAQ pullback RSI {rsi14:.0f}")

    if macd["bull_cross"]:
        score += 2
        reasons.append("MACD bullish cross")
    elif macd["hist"] > 0:
        score += 1
        reasons.append("MACD positive")

    if len(prices) >= 21:
        prev_lo, _prev_mid, _prev_hi = calc_bollinger(prices[:-1], 20)
        if prev < prev_lo and current >= bb_lo:
            score += 2
            reasons.append("Bollinger rebound")
        elif current <= bb_lo:
            score += 1
            reasons.append("near lower band")

    if len(prices) >= 60 and current > sma60 and rsi2 <= 20:
        score += 2
        reasons.append(f"trend pullback RSI2={rsi2:.0f}")
    elif len(prices) >= 120 and current > sma120 and rsi2 <= 25:
        score += 1
        reasons.append(f"long trend pullback RSI2={rsi2:.0f}")

    if len(highs) >= 21 and len(volumes) >= 20:
        high20 = max(highs[-21:-1])
        vol_avg = sum(volumes[-20:]) / 20
        if current > high20 and volumes[-1] > vol_avg * 1.4:
            score += 2
            reasons.append("20-day breakout with volume")
        elif volumes[-1] > vol_avg * 1.5:
            score += 1
            reasons.append("volume spike")

    return {
        "score": score,
        "reasons": reasons or ["no signal"],
        "rsi": rsi14,
        "rsi2": rsi2,
        "macd_hist": float(macd.get("hist", 0.0) or 0.0),
        "sma20": sma20,
        "sma60": sma60,
        "price": current,
    }


def fetch_history(symbol: str, period: str = "6mo") -> dict[str, list[float]]:
    from src.online_access import require_online_access

    require_online_access("Mistock market-data download")
    data = yf.download(
        normalize_symbol(symbol),
        period=period,
        interval="1d",
        auto_adjust=False,
        progress=False,
        threads=False,
        timeout=config.yfinance_timeout_seconds,
    )
    if data is None or data.empty:
        return {"close": [], "high": [], "volume": []}
    close = data["Close"]
    high = data["High"]
    volume = data["Volume"]
    if hasattr(close, "iloc") and len(getattr(close, "shape", [])) > 1:
        close = close.iloc[:, 0]
        high = high.iloc[:, 0]
        volume = volume.iloc[:, 0]
    return {
        "close": [float(v) for v in close.dropna().tolist() if math.isfinite(float(v))],
        "high": [float(v) for v in high.dropna().tolist() if math.isfinite(float(v))],
        "volume": [float(v) for v in volume.dropna().tolist() if math.isfinite(float(v))],
    }


def quote(symbol: str) -> dict[str, float]:
    hist = fetch_history(symbol, period="5d")
    price = hist["close"][-1] if hist["close"] else 0.0
    return {"current": price, "ask1": price, "bid1": price}
