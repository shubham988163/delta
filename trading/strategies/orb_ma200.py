"""Opening Range Breakout (ORB) + 200 EMA Trend Filter Strategy.

Adapted for 24/7 crypto and tokenized stocks.
Uses session windows (e.g., Daily UTC 00:00-00:30, London 08:00-08:30 UTC,
or NY 13:30-14:00 UTC) with 200 EMA trend gating and ATR-based structural stops.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
import pandas as pd

from trading.config import RR_TARGET
from trading.strategies.base import BaseStrategy, Signal


class OrbMa200Strategy(BaseStrategy):
    """ORB + MA200 Strategy for Delta Exchange Instruments."""

    def __init__(
        self,
        name: str = "ORB_MA200",
        or_bars: int = 4,  # First 4 bars of the session define the range (e.g. 1 hour on 15m)
        rr: float = RR_TARGET,
        atr_buffer: float = 0.5,
    ):
        super().__init__(name=name)
        self.or_bars = or_bars
        self.rr = rr
        self.atr_buffer = atr_buffer

    def generate_signal(self, symbol: str, df: pd.DataFrame, ltp: float) -> Optional[Signal]:
        if df.empty or len(df) < 50:
            return None

        # Look at the most recent finished bars
        last_bar = df.iloc[-1]
        prev_bar = df.iloc[-2]

        close = float(last_bar["close"])
        ema_200 = float(last_bar["ema_200"])
        atr = float(last_bar["atr"])

        if pd.isna(ema_200) or pd.isna(atr) or atr <= 0:
            return None

        # Calculate session rolling opening range over the last N bars
        lookback_df = df.iloc[-self.or_bars - 2 : -2]
        if lookback_df.empty:
            return None

        range_high = float(lookback_df["high"].max())
        range_low = float(lookback_df["low"].min())

        now_str = datetime.now(timezone.utc).isoformat()

        # LONG BREAKOUT:
        # 1. Price above 200 EMA (Uptrend gate)
        # 2. Fresh breakout above range high
        if close > range_high and prev_bar["close"] <= range_high and close > ema_200:
            stop_loss = round(range_low - (self.atr_buffer * atr), 4)
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
                rationale=f"Bullish ORB breakout above {range_high:.2f} & > EMA200 ({ema_200:.2f})",
                timestamp=now_str,
            )

        # SHORT BREAKOUT:
        # 1. Price below 200 EMA (Downtrend gate)
        # 2. Fresh breakdown below range low
        if close < range_low and prev_bar["close"] >= range_low and close < ema_200:
            stop_loss = round(range_high + (self.atr_buffer * atr), 4)
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
                rationale=f"Bearish ORB breakdown below {range_low:.2f} & < EMA200 ({ema_200:.2f})",
                timestamp=now_str,
            )

        return None
