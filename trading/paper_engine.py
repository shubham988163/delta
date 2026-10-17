"""Paper Trading Matching Engine for Delta Exchange Instruments.

Simulates real-time fills, slippage, taker fees, stop-loss triggers,
take-profit triggers, and trailing stops against live Delta Exchange mark prices.
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional

from trading.config import (
    PAPER_INITIAL_CAPITAL,
    SLIPPAGE_PCT,
    TAKER_FEE_PCT,
    TRAILING_STOP_ENABLED,
    BREAKEVEN_AT_R,
)
from trading.ledger import Ledger

logger = logging.getLogger(__name__)


@dataclass
class PaperPosition:
    trade_id: str
    symbol: str
    side: str  # 'BUY' or 'SELL'
    contracts: int
    contract_value: float
    entry_price: float
    stop_loss: float
    take_profit: float
    initial_risk: float
    highest_price: float
    lowest_price: float
    breakeven_armed: bool = False
    open_time: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def current_pnl(self, mark_price: float) -> float:
        """Calculate unrealized PnL in USD."""
        notional_qty = self.contracts * self.contract_value
        if self.side == "BUY":
            return (mark_price - self.entry_price) * notional_qty
        else:
            return (self.entry_price - mark_price) * notional_qty


class PaperEngine:
    """Simulated execution engine with realistic fill and fee mechanics."""

    def __init__(self, initial_capital: float = PAPER_INITIAL_CAPITAL, ledger: Optional[Ledger] = None):
        self.balance = initial_capital
        self.ledger = ledger or Ledger()
        self.open_positions: Dict[str, PaperPosition] = {}
        self._load_open_positions_from_db()

    def _load_open_positions_from_db(self) -> None:
        """Sync open positions from sqlite ledger on startup."""
        db_positions = self.ledger.get_open_trades(mode="paper")
        for row in db_positions:
            t_id = row["trade_id"]
            side = row["side"]
            contracts = int(row["contracts"])
            entry = float(row["entry_price"])
            sl = float(row["stop_loss"])
            tp = float(row["take_profit"])
            # Default contract value assumption if not saved
            c_val = 0.001 if "BTC" in row["symbol"] else (0.01 if "ETH" in row["symbol"] else 1.0)
            risk = abs(entry - sl) * contracts * c_val

            self.open_positions[t_id] = PaperPosition(
                trade_id=t_id,
                symbol=row["symbol"],
                side=side,
                contracts=contracts,
                contract_value=c_val,
                entry_price=entry,
                stop_loss=sl,
                take_profit=tp,
                initial_risk=risk,
                highest_price=entry,
                lowest_price=entry,
            )

    def open_position(
        self,
        symbol: str,
        side: str,
        contracts: int,
        mark_price: float,
        stop_loss: float,
        take_profit: float,
        contract_value: float = 1.0,
    ) -> Optional[PaperPosition]:
        """Simulate order execution with slippage and taker fee."""
        trade_id = f"paper_{uuid.uuid4().hex[:8]}"

        # Apply realistic slippage: BUY enters higher, SELL enters lower
        slip_multiplier = (1.0 + SLIPPAGE_PCT) if side == "BUY" else (1.0 - SLIPPAGE_PCT)
        fill_price = round(mark_price * slip_multiplier, 4)

        notional_value = fill_price * contracts * contract_value
        fee = notional_value * TAKER_FEE_PCT
        slippage_cost = abs(fill_price - mark_price) * contracts * contract_value

        self.balance -= fee
        initial_risk = abs(fill_price - stop_loss) * contracts * contract_value

        pos = PaperPosition(
            trade_id=trade_id,
            symbol=symbol,
            side=side,
            contracts=contracts,
            contract_value=contract_value,
            entry_price=fill_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            initial_risk=initial_risk,
            highest_price=fill_price,
            lowest_price=fill_price,
        )
        self.open_positions[trade_id] = pos

        # Record to ledger
        self.ledger.record_entry(
            trade_id=trade_id,
            symbol=symbol,
            side=side,
            contracts=contracts,
            entry_price=fill_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            fees=fee,
            slippage=slippage_cost,
            mode="paper",
        )
        logger.info(
            f"[PAPER] OPEN {side} {contracts}x {symbol} @ {fill_price} | SL: {stop_loss} | TP: {take_profit} | Fee: ${fee:.2f}"
        )
        return pos

    def close_position(
        self, trade_id: str, exit_price: float, reason: str
    ) -> Optional[float]:
        """Close an open paper position and settle PnL."""
        pos = self.open_positions.pop(trade_id, None)
        if not pos:
            return None

        # Slippage on exit
        slip_multiplier = (1.0 - SLIPPAGE_PCT) if pos.side == "BUY" else (1.0 + SLIPPAGE_PCT)
        actual_exit = round(exit_price * slip_multiplier, 4)

        notional_value = actual_exit * pos.contracts * pos.contract_value
        exit_fee = notional_value * TAKER_FEE_PCT
        raw_pnl = pos.current_pnl(actual_exit)
        net_pnl = raw_pnl - exit_fee

        self.balance += net_pnl
        self.ledger.record_exit(
            trade_id=trade_id,
            exit_price=actual_exit,
            realized_pnl=net_pnl,
            exit_reason=reason,
            add_fees=exit_fee,
        )
        logger.info(
            f"[PAPER] CLOSE {pos.symbol} @ {actual_exit} ({reason}) | PnL: ${net_pnl:+.2f} | Balance: ${self.balance:.2f}"
        )
        return net_pnl

    def evaluate_ticks(self, live_prices: Dict[str, float]) -> List[str]:
        """Check all open positions against live prices for SL, TP, and trailing stops."""
        closed_ids = []
        for t_id, pos in list(self.open_positions.items()):
            price = live_prices.get(pos.symbol)
            if not price or price <= 0:
                continue

            pos.highest_price = max(pos.highest_price, price)
            pos.lowest_price = min(pos.lowest_price, price)

            # 1. Breakeven / Trailing stop logic
            if TRAILING_STOP_ENABLED and pos.initial_risk > 0:
                current_pnl = pos.current_pnl(price)
                if current_pnl >= (pos.initial_risk * BREAKEVEN_AT_R) and not pos.breakeven_armed:
                    pos.breakeven_armed = True
                    pos.stop_loss = pos.entry_price
                    logger.info(f"[PAPER] Breakeven armed for {pos.symbol} @ {pos.entry_price}")

            # 2. Check Stop Loss
            if pos.side == "BUY" and price <= pos.stop_loss:
                self.close_position(t_id, price, "STOP_LOSS")
                closed_ids.append(t_id)
            elif pos.side == "SELL" and price >= pos.stop_loss:
                self.close_position(t_id, price, "STOP_LOSS")
                closed_ids.append(t_id)

            # 3. Check Take Profit
            elif pos.side == "BUY" and price >= pos.take_profit:
                self.close_position(t_id, price, "TAKE_PROFIT")
                closed_ids.append(t_id)
            elif pos.side == "SELL" and price <= pos.take_profit:
                self.close_position(t_id, price, "TAKE_PROFIT")
                closed_ids.append(t_id)

        return closed_ids
