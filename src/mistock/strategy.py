from __future__ import annotations

import math
from typing import Any

import yfinance as yf

from src.mistock.config import config
from src.strategy.indicators import calc_bollinger, calc_macd, calc_rsi, calc_sma

def fetch_wikipedia_universe() -> list[str]:
    import pandas as pd
    import requests
    from src.utils.logger import logger

    symbols = []

    # 1단계: Nasdaq-100 크롤링
    try:
        url = "https://en.wikipedia.org/wiki/Nasdaq-100"
        headers = {"User-Agent": "Mozilla/5.0"}
        resp = requests.get(url, headers=headers, timeout=5)
        if resp.status_code == 200:
            tables = pd.read_html(resp.text)
            for table in tables:
                if "Ticker" in table.columns or "Symbol" in table.columns:
                    col = "Ticker" if "Ticker" in table.columns else "Symbol"
                    tickers = table[col].dropna().tolist()
                    if len(tickers) >= 80:
                        symbols.extend([str(t).strip().upper() for t in tickers])
                        break
    except Exception as e:
        logger.warning(f"Failed to fetch dynamic NASDAQ-100 from wikipedia: {e}")

    # 2단계: S&P 500 크롤링 (폴백 및 확장)
    if len(symbols) < 50:
        try:
            url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
            headers = {"User-Agent": "Mozilla/5.0"}
            resp = requests.get(url, headers=headers, timeout=5)
            if resp.status_code == 200:
                tables = pd.read_html(resp.text)
                for table in tables:
                    if "Symbol" in table.columns or "Ticker" in table.columns:
                        col = "Symbol" if "Symbol" in table.columns else "Ticker"
                        tickers = table[col].dropna().tolist()
                        if len(tickers) >= 400:
                            symbols.extend([str(t).strip().upper() for t in tickers[:120]])
                            break
        except Exception as e:
            logger.warning(f"Failed to fetch dynamic S&P 500 from wikipedia: {e}")

    # 중복 제거 및 정규화
    unique_symbols = []
    seen = set()
    for s in symbols:
        norm = normalize_symbol(s)
        if norm and norm not in seen:
            seen.add(norm)
            unique_symbols.append(norm)

    return unique_symbols


def build_scan_universe(api: Any = None) -> list[str]:
    from src.utils.logger import logger

    # 1순위: KIS API가 제공되면 해외주식 거래대금 상위 종목을 동적으로 가져온다.
    if api is not None:
        try:
            nas_symbols = api.get_overseas_volume_rank(excd="NAS", cnt=50)
            nys_symbols = api.get_overseas_volume_rank(excd="NYS", cnt=50)
            combined = list(dict.fromkeys(nas_symbols + nys_symbols))
            if len(combined) >= 20:
                logger.info(f"[MISTOCK] KIS API 해외 거래대금 상위 {len(combined)}종목 동적 수집 완료")
                return combined
        except Exception as exc:
            logger.warning(f"[MISTOCK] KIS 해외 순위 API 조회 실패: {exc}")

    # 2순위: Online Wikipedia 크롤링
    wiki_symbols = fetch_wikipedia_universe()
    if len(wiki_symbols) >= 30:
        logger.info(f"[MISTOCK] Wikipedia Nasdaq-100 / S&P500 {len(wiki_symbols)}종목 동적 크롤링 완료")
        return wiki_symbols

    # 3순위: 하드코딩 정적 풀 폴백
    logger.info(f"[MISTOCK] 동적 수집 실패 -> config.universe_list 정적 풀 {len(config.universe_list)}종목으로 폴백")
    return list(config.universe_list)


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
