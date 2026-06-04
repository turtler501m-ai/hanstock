"""
Template for custom strategy rules.
Users can place new strategy files in this directory to register and load them.
"""

class CustomRSILimitStrategy:
    """
    A custom trading strategy that triggers buy signals based on oversold RSI,
    bullish MACD crossovers, and price position below Bollinger Bands.
    """
    def __init__(self, rsi_period: int = 14, buy_threshold: float = 30.0):
        self.rsi_period = rsi_period
        self.buy_threshold = buy_threshold

    def calculate_score(self, prices: list[float], indicators: dict) -> float:
        """
        Calculates a trade recommendation score between 0.0 and 5.0.
        """
        score = 0.0
        rsi = indicators.get("rsi", 50.0)
        macd = indicators.get("macd_hist", 0.0)
        current = prices[-1] if prices else 0.0
        bb_lo = indicators.get("bb_lo", current)
        
        # 1. RSI oversold criteria
        if rsi < self.buy_threshold:
            score += 2.0
        elif rsi < 45.0:
            score += 0.5
            
        # 2. MACD histogram positive trend
        if macd > 0:
            score += 1.5
            
        # 3. Bollinger Band bottom boundary touch
        if current < bb_lo:
            score += 1.5
            
        return min(5.0, score)
