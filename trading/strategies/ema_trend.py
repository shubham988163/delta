"""EMA Trend-Following Strategy (9 / 21 Crossover with 200 EMA Filter).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
import pandas as pd

from trading.config import RR_TARGET
from trading.strategies.base import BaseStrategy, Signal


class EmaTrendStrategy(BaseStrategy):
    """EMA 9/21 Crossover filtered by 200 EMA."""

    def __init__(self, name: str = "EMA_TREND", rr: float = RR_TARGET, atr_mult: float = 1.5):
        super().__init__(name=name)
        self.rr = rr
        self.atr_mult = atr_mult

    def generate_signal(self, symbol: str, df: pd.DataFrame, ltp: float) -> Optional[Signal]:
        if df.empty or len(df) < 30:
            return None

        curr = df.iloc[-1]
        prev = df.iloc[-2]

        close = float(curr["close"])
        ema_9 = float(curr["ema_9"])
        ema_21 = float(curr["ema_21"])
        ema_200 = float(curr["ema_200"])
        atr = float(curr["atr"])

        prev_ema_9 = float(prev["ema_9"])
        prev_ema_21 = float(prev["ema_21"])

        if pd.isna(ema_200) or pd.isna(atr) or atr <= 0:
            return None

        now_str = datetime.now(timezone.utc).isoformat()

        # Bullish cross: EMA 9 crosses above EMA 21 while above 200 EMA
        if prev_ema_9 <= prev_ema_21 and ema_9 > ema_21 and close > ema_200:
            stop_loss = round(close - (self.atr_mult * atr), 4)
            risk = close - stop_loss
            if risk <= 0:
                return None
            take_profit = round(close + (self.rr * risk), 4)
            return Signal(
                symbol=symbol,
                side="BUY",
                entry_price=close,
                stop_loss=stop_loss,
                take_profit=take_profit,
                strategy_name=self.name,
                rationale=f"Bullish EMA 9/21 cross above EMA200 ({ema_200:.2f})",
                timestamp=now_str,
            )

        # Bearish cross: EMA 9 crosses below EMA 21 while below 200 EMA
        if prev_ema_9 >= prev_ema_21 and ema_9 < ema_21 and close < ema_200:
            stop_loss = round(close + (self.atr_mult * atr), 4)
            risk = stop_loss - close
            if risk <= 0:
                return None
            take_profit = round(close - (self.rr * risk), 4)
            return Signal(
                symbol=symbol,
                side="SELL",
                entry_price=close,
                stop_loss=stop_loss,
                take_profit=take_profit,
                strategy_name=self.name,
                rationale=f"Bearish EMA 9/21 cross below EMA200 ({ema_200:.2f})",
                timestamp=now_str,
            )

        return None
