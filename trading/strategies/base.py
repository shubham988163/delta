"""Base strategy classes and signal definitions.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional
import pandas as pd


@dataclass
class Signal:
    symbol: str
    side: str  # 'BUY' or 'SELL'
    entry_price: float
    stop_loss: float
    take_profit: float
    strategy_name: str
    rationale: str
    timestamp: str

    def to_dict(self) -> Dict:
        return {
            "symbol": self.symbol,
            "side": self.side,
            "entry_price": self.entry_price,
            "stop_loss": self.stop_loss,
            "take_profit": self.take_profit,
            "strategy_name": self.strategy_name,
            "rationale": self.rationale,
            "timestamp": self.timestamp,
        }


class BaseStrategy:
    """Abstract Strategy interface."""

    def __init__(self, name: str):
        self.name = name

    def generate_signal(self, symbol: str, df: pd.DataFrame, ltp: float) -> Optional[Signal]:
        raise NotImplementedError
