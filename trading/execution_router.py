"""Execution Router & Hard Risk Safety Kernel.

Hard risk limits live HERE, not in strategies or agents. A bug or rogue signal
can never exceed these guardrails. Routes orders to PaperEngine in paper mode,
or DeltaClient in live mode.
"""
from __future__ import annotations

import logging
import time
from typing import Any, Dict, Optional

from trading.config import (
    TRADING_MODE,
    DAILY_LOSS_LIMIT_USD,
    DAILY_PROFIT_TARGET_USD,
    MAX_OPEN_POSITIONS,
    MAX_POSITION_VALUE_USD,
    MAX_ORDERS_PER_SEC,
    RISK_PER_TRADE_USD,
)
from trading.delta_client import DeltaClient
from trading.ledger import Ledger
from trading.paper_engine import PaperEngine

logger = logging.getLogger(__name__)


class RateLimiter:
    """Sliding one-second window rate limiter."""

    def __init__(self, max_per_sec: int = MAX_ORDERS_PER_SEC):
        self.max_per_sec = max_per_sec
        self._timestamps: list[float] = []

    def allow(self) -> bool:
        now = time.monotonic()
        self._timestamps = [t for t in self._timestamps if now - t < 1.0]
        if len(self._timestamps) >= self.max_per_sec:
            return False
        self._timestamps.append(now)
        return True


class ExecutionRouter:
    """Safety kernel and trade dispatcher."""

    def __init__(
        self,
        mode: str = TRADING_MODE,
        ledger: Optional[Ledger] = None,
        delta_client: Optional[DeltaClient] = None,
        paper_engine: Optional[PaperEngine] = None,
    ):
        assert mode in ("paper", "live"), f"Invalid mode: {mode}"
        self.mode = mode
        self.ledger = ledger or Ledger()
        self.delta_client = delta_client or DeltaClient()
        self.paper_engine = paper_engine or PaperEngine(ledger=self.ledger)
        self.rate_limiter = RateLimiter()

    def risk_check(self, signal: Dict[str, Any], mark_price: float) -> Optional[str]:
        """Evaluate hard risk constraints. Returns rejection reason or None if accepted."""
        # 1. Rate limiter
        if not self.rate_limiter.allow():
            return "REJECTED: Rate limit exceeded (too many orders per second)"

        # 2. Daily Loss Limit
        today_pnl = self.ledger.get_today_pnl(self.mode)
        if today_pnl <= DAILY_LOSS_LIMIT_USD:
            return f"REJECTED: Daily loss limit hit (${today_pnl:.2f} <= ${DAILY_LOSS_LIMIT_USD:.2f})"

        # 3. Daily Profit Target
        if today_pnl >= DAILY_PROFIT_TARGET_USD:
            return f"REJECTED: Daily profit target reached (${today_pnl:.2f} >= ${DAILY_PROFIT_TARGET_USD:.2f})"

        # 4. Max Open Positions
        open_positions = (
            list(self.paper_engine.open_positions.values())
            if self.mode == "paper"
            else self.ledger.get_open_trades("live")
        )
        if len(open_positions) >= MAX_OPEN_POSITIONS:
            return f"REJECTED: Max open positions cap reached ({len(open_positions)}/{MAX_OPEN_POSITIONS})"

        # 5. Check if symbol already has an open position
        symbol = signal.get("symbol")
        for pos in open_positions:
            pos_sym = pos.symbol if hasattr(pos, "symbol") else pos.get("symbol")
            if pos_sym == symbol:
                return f"REJECTED: Position already open for {symbol}"

        # 6. Stop loss validity
        entry = float(signal.get("entry_price") or mark_price)
        sl = float(signal.get("stop_loss", 0.0))
        side = signal.get("side", "").upper()
        if side == "BUY" and sl >= entry:
            return f"REJECTED: Invalid BUY stop loss ({sl} >= {entry})"
        if side == "SELL" and sl <= entry:
            return f"REJECTED: Invalid SELL stop loss ({sl} <= {entry})"

        return None

    def calculate_position_size(
        self, symbol: str, entry_price: float, stop_loss: float
    ) -> tuple[int, float]:
        """Calculate number of contracts based on RISK_PER_TRADE_USD and contract specs."""
        prod = self.delta_client.get_product(symbol)
        contract_value = float(prod.get("contract_value", 1.0)) if prod else 1.0

        risk_per_contract = abs(entry_price - stop_loss) * contract_value
        if risk_per_contract <= 0:
            return 1, contract_value

        contracts = int(RISK_PER_TRADE_USD / risk_per_contract)
        contracts = max(1, contracts)

        # Enforce MAX_POSITION_VALUE_USD cap
        notional = contracts * contract_value * entry_price
        if notional > MAX_POSITION_VALUE_USD:
            contracts = max(1, int(MAX_POSITION_VALUE_USD / (contract_value * entry_price)))

        return contracts, contract_value

    def dispatch(self, signal: Dict[str, Any], mark_price: float) -> Dict[str, Any]:
        """Run risk checks and dispatch order to paper engine or live broker."""
        rejection = self.risk_check(signal, mark_price)
        if rejection:
            logger.warning(f"[{self.mode.upper()}] {rejection}")
            return {"status": "REJECTED", "reason": rejection}

        symbol = signal["symbol"]
        side = signal["side"].upper()
        sl = float(signal["stop_loss"])
        tp = float(signal["take_profit"])

        contracts, contract_value = self.calculate_position_size(symbol, mark_price, sl)

        if self.mode == "paper":
            pos = self.paper_engine.open_position(
                symbol=symbol,
                side=side,
                contracts=contracts,
                mark_price=mark_price,
                stop_loss=sl,
                take_profit=tp,
                contract_value=contract_value,
            )
            return {"status": "FILLED", "mode": "paper", "trade_id": pos.trade_id, "contracts": contracts}

        elif self.mode == "live":
            prod_id = self.delta_client.get_product_id(symbol)
            if not prod_id:
                return {"status": "ERROR", "reason": f"Product ID not found for {symbol}"}

            res = self.delta_client.place_order(
                product_id=prod_id,
                size=contracts,
                side=side.lower(),
                order_type="market_order",
            )
            if res.get("success"):
                return {"status": "FILLED", "mode": "live", "response": res}
            else:
                return {"status": "ERROR", "reason": res.get("error", "Unknown Delta API error")}

        return {"status": "ERROR", "reason": "Invalid mode"}
