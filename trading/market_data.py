"""Market data provider for Delta Exchange instruments.

Fetches live tickers and historical OHLCV candles, converts to DataFrames,
and computes technical indicators (EMA, ATR, VWAP, RSI).
"""
from __future__ import annotations

import logging
from typing import Dict, Optional
import numpy as np
import pandas as pd

from trading.delta_client import DeltaClient

logger = logging.getLogger(__name__)


class MarketDataProvider:
    """Provides processed market data for strategies."""

    def __init__(self, client: Optional[DeltaClient] = None):
        self.client = client or DeltaClient()
        self._ticker_cache: Dict[str, Dict] = {}

    def get_ltp(self, symbol: str) -> float:
        """Get Last Traded Price (LTP) or mark price for a symbol."""
        ticker = self.client.get_ticker(symbol)
        if ticker:
            self._ticker_cache[symbol.upper()] = ticker
            # Prefer mark_price or close
            val = ticker.get("mark_price") or ticker.get("close")
            if val is not None:
                return float(val)
        return 0.0

    def get_best_bid_ask(self, symbol: str) -> tuple[float, float]:
        """Get best bid and ask from ticker quotes."""
        ticker = self.client.get_ticker(symbol)
        if ticker and "quotes" in ticker:
            quotes = ticker["quotes"]
            bid = float(quotes.get("best_bid") or 0.0)
            ask = float(quotes.get("best_ask") or 0.0)
            if bid > 0 and ask > 0:
                return bid, ask
        ltp = self.get_ltp(symbol)
        return ltp, ltp

    def get_candles_df(
        self, symbol: str, resolution: str = "15m", count: int = 150
    ) -> pd.DataFrame:
        """Fetch historical candles and convert to a technical indicator DataFrame.
        
        Columns returned: open, high, low, close, volume, ema_9, ema_21, ema_200, atr, vwap.
        """
        # Calculate time span based on resolution
        mins = 15
        if resolution.endswith("m"):
            mins = int(resolution[:-1])
        elif resolution.endswith("h"):
            mins = int(resolution[:-1]) * 60
        elif resolution.endswith("d"):
            mins = int(resolution[:-1]) * 1440

        import time
        now = int(time.time())
        start = now - (mins * 60 * (count + 50))

        raw_candles = self.client.get_candles(symbol, resolution=resolution, start=start, end=now)
        if not raw_candles:
            return pd.DataFrame()

        df = pd.DataFrame(raw_candles)
        # Delta fields: close, high, low, open, time, volume
        df["datetime"] = pd.to_datetime(df["time"], unit="s", utc=True)
        df.set_index("datetime", inplace=True)
        df.sort_index(inplace=True)

        for col in ["open", "high", "low", "close", "volume"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")

        # Technical Indicators
        df["ema_9"] = df["close"].ewm(span=9, adjust=False).mean()
        df["ema_21"] = df["close"].ewm(span=21, adjust=False).mean()
        df["ema_200"] = df["close"].ewm(span=200, adjust=False).mean()

        # ATR (14)
        high_low = df["high"] - df["low"]
        high_close = (df["high"] - df["close"].shift()).abs()
        low_close = (df["low"] - df["close"].shift()).abs()
        tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        df["atr"] = tr.rolling(window=14).mean()

        # Session / Rolling VWAP
        typical_price = (df["high"] + df["low"] + df["close"]) / 3.0
        cum_vol_price = (typical_price * df["volume"]).cumsum()
        cum_vol = df["volume"].cumsum()
        df["vwap"] = cum_vol_price / cum_vol.replace(0, np.nan)

        return df
