"""
Mock Trading with Real-Time Prices
한국투자 KIS API + Binance fallback
"""
import json
import os
import time
import requests
from datetime import datetime
from typing import Optional, Dict

try:
    from src.api.kis_futures_api import KISFuturesAPI
    KIS_API_AVAILABLE = True
except ImportError:
    KIS_API_AVAILABLE = False


class PriceFetcher:
    """실제 시세 조회 (한국투자 KIS API 우선, Binance fallback)"""
    
    # Telegram symbol -> 한국투자 종목코드
    SYMBOL_MAP_KIS = {
        "NQ": "NQH26",   # 나스닥NQ
        "MNQ": "MNQH26", # 마이크로나스닥
        "ES": "ESH26",   # S&P500
        "GC": "GCH26",   # 골드
        "CL": "CLH26",   # 원유
        "HSI": "HSIH26", # 항셍
    }
    
    # Binance symbol mapping (fallback)
    SYMBOL_MAP_BINANCE = {
        "BTC": "BTCUSDT",
        "ETH": "ETHUSDT",
    }
    
    def __init__(self):
        self.kis_api = None
        if KIS_API_AVAILABLE:
            try:
                self.kis_api = KISFuturesAPI()
            except Exception as e:
                print(f"KIS API init error: {e}")
    
    def get_price(self, symbol: str) -> float:
        """단일 시세 조회 - 한국투자 우선"""
        
        # 1. 한국투자 API 시도
        if self.kis_api:
            try:
                kis_code = self.SYMBOL_MAP_KIS.get(symbol)
                if kis_code:
                    price = self._get_kis_price(kis_code)
                    if price > 0:
                        print(f"[KIS] {symbol} = ${price}")
                        return price
            except Exception as e:
                print(f"KIS price error for {symbol}: {e}")
        
        # 2. Binance fallback
        binance_symbol = self.SYMBOL_MAP_BINANCE.get(symbol, symbol + "USDT")
        try:
            url = f"https://api.binance.com/api/v3/ticker/price?symbol={binance_symbol}"
            resp = requests.get(url, timeout=5)
            return float(resp.json()['price'])
        except Exception as e:
            print(f"Binance price error for {symbol}: {e}")
            return 0
    
    def _get_kis_price(self, kis_code: str) -> float:
        """한국투자에서 시세 조회"""
        if not self.kis_api:
            return 0
        
        try:
            # 해외선물 현재가 조회
            result = self.kis_api.get_current_price(kis_code)
            if result and "output" in result:
                price = result["output"].get("last")
                if price:
                    return float(price)
        except Exception as e:
            print(f"KIS API error: {e}")
        
        return 0
    
    @staticmethod
    def get_prices(symbols: list) -> Dict[str, float]:
        """여러 시세 조회"""
        fetcher = PriceFetcher()
        prices = {}
        for sym in symbols:
            prices[sym] = fetcher.get_price(sym)
        return prices


# Keep backward compatibility
def get_price(symbol: str) -> float:
    return PriceFetcher().get_price(symbol)


def get_prices(symbols: list) -> Dict[str, float]:
    return PriceFetcher.get_prices(symbols)