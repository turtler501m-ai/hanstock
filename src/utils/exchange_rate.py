# -*- coding: utf-8 -*-
from __future__ import annotations

import time
import yfinance as yf
from src.utils.logger import logger

_USD_KRW_RATE: float = 1380.0
_USD_KRW_LAST_FETCH: float = 0.0
_USD_KRW_CACHE_TTL: float = 3600.0  # 1 hour cache

def get_usd_krw_rate() -> float:
    global _USD_KRW_RATE, _USD_KRW_LAST_FETCH
    now = time.time()
    if now - _USD_KRW_LAST_FETCH > _USD_KRW_CACHE_TTL:
        try:
            ticker = yf.Ticker("USDKRW=X")
            info = ticker.fast_info
            rate = info.get("last_price") or info.get("lastPrice")
            if not rate:
                hist = ticker.history(period="1d")
                if not hist.empty:
                    rate = float(hist["Close"].iloc[-1])
            if rate and rate > 0:
                _USD_KRW_RATE = float(rate)
                _USD_KRW_LAST_FETCH = now
        except Exception as e:
            logger.warning(f"Failed to fetch USD/KRW rate from yfinance: {e}")
            _USD_KRW_LAST_FETCH = now - _USD_KRW_CACHE_TTL + 300  # retry in 5 mins
    return _USD_KRW_RATE
