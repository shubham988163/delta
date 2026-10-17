"""Main Trading Loop & Live Console Dashboard for Delta Exchange.

Supports seamless Paper Trading (default) and Live Trading.
Scans watchlist, updates market prices, processes strategy signals,
manages open positions, and enforces risk kernel limits.
"""
from __future__ import annotations

import logging
import os
import sys
import time
from datetime import datetime, timezone
from tabulate import tabulate

from trading.config import (
    TRADING_MODE,
    WATCHLIST,
    CANDLE_TIMEFRAME,
    POLL_INTERVAL_SECONDS,
    DAILY_LOSS_LIMIT_USD,
    DAILY_PROFIT_TARGET_USD,
    RISK_PER_TRADE_USD,
    DELTA_BASE_URL,
)
from trading.delta_client import DeltaClient
from trading.execution_router import ExecutionRouter
from trading.ledger import Ledger
from trading.market_data import MarketDataProvider
from trading.paper_engine import PaperEngine
from trading.strategies.orb_ma200 import OrbMa200Strategy
from trading.strategies.ema_trend import EmaTrendStrategy

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("TRADER")


def clear_screen():
    os.system("cls" if os.name == "nt" else "clear")


def main():
    print("=" * 75)
    print("   DELTA EXCHANGE AUTOMATED TRADING SYSTEM   ")
    print("=" * 75)
    print(f"Mode               : {TRADING_MODE.upper()}")
    print(f"Delta API Endpoint : {DELTA_BASE_URL}")
    print(f"Watchlist          : {', '.join(WATCHLIST)}")
    print(f"Timeframe          : {CANDLE_TIMEFRAME}")
    print(f"Risk Per Trade     : ${RISK_PER_TRADE_USD:.2f}")
    print(f"Daily Limits       : Loss ${DAILY_LOSS_LIMIT_USD:.2f} | Profit Target ${DAILY_PROFIT_TARGET_USD:.2f}")
    print("=" * 75)

    client = DeltaClient()
    market_data = MarketDataProvider(client=client)
    ledger = Ledger()
    paper_engine = PaperEngine(ledger=ledger)
    router = ExecutionRouter(
        mode=TRADING_MODE,
        ledger=ledger,
        delta_client=client,
        paper_engine=paper_engine,
    )

    strategies = [
        OrbMa200Strategy(),
        EmaTrendStrategy(),
    ]

    iteration = 0
    try:
        while True:
            iteration += 1
            now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
            print(f"\n--- Iteration #{iteration} | {now_utc} ---")

            live_prices = {}
            market_rows = []

            # 1. Fetch live market quotes
            for symbol in WATCHLIST:
                try:
                    ltp = market_data.get_ltp(symbol)
                    live_prices[symbol] = ltp
                    market_rows.append({"Symbol": symbol, "LTP": f"${ltp:,.2f}" if ltp > 0 else "N/A"})
                except Exception as e:
                    logger.error(f"Error fetching LTP for {symbol}: {e}")

            # 2. Evaluate open positions against latest ticks (SL, TP, Breakeven)
            if TRADING_MODE == "paper":
                closed_ids = paper_engine.evaluate_ticks(live_prices)
                if closed_ids:
                    logger.info(f"Closed positions on SL/TP: {closed_ids}")

            # 3. Strategy Scanning & Signal Generation
            for symbol in WATCHLIST:
                ltp = live_prices.get(symbol, 0.0)
                if ltp <= 0:
                    continue

                try:
                    df = market_data.get_candles_df(symbol, resolution=CANDLE_TIMEFRAME, count=100)
                    if df.empty:
                        continue

                    for strat in strategies:
                        signal = strat.generate_signal(symbol, df, ltp)
                        if signal:
                            logger.info(f"Signal Generated: {signal.side} {symbol} ({signal.rationale})")
                            res = router.dispatch(signal.to_dict(), mark_price=ltp)
                            logger.info(f"Dispatch Result: {res}")
                            break  # one signal per symbol per cycle
                except Exception as e:
                    logger.error(f"Error scanning {symbol}: {e}")

            # 4. Display Dashboard
            today_pnl = ledger.get_today_pnl(TRADING_MODE)
            trade_count = ledger.get_trade_count_today(TRADING_MODE)

            print("\n[MARKET STATUS]")
            print(tabulate(market_rows, headers="keys", tablefmt="simple"))

            print(f"\n[PERFORMANCE] Mode: {TRADING_MODE.upper()} | Today PnL: ${today_pnl:+.2f} | Trades Today: {trade_count}")

            if TRADING_MODE == "paper":
                open_pos = paper_engine.open_positions
                print(f"[PAPER WALLET] Balance: ${paper_engine.balance:,.2f} | Open Positions: {len(open_pos)}")
                if open_pos:
                    pos_rows = []
                    for t_id, p in open_pos.items():
                        cur_price = live_prices.get(p.symbol, p.entry_price)
                        u_pnl = p.current_pnl(cur_price)
                        pos_rows.append({
                            "ID": t_id,
                            "Symbol": p.symbol,
                            "Side": p.side,
                            "Size": p.contracts,
                            "Entry": f"${p.entry_price:.2f}",
                            "Current": f"${cur_price:.2f}",
                            "SL": f"${p.stop_loss:.2f}",
                            "TP": f"${p.take_profit:.2f}",
                            "PnL ($)": f"{u_pnl:+.2f}",
                        })
                    print(tabulate(pos_rows, headers="keys", tablefmt="simple"))

            print(f"\nNext scan in {POLL_INTERVAL_SECONDS} seconds... (Press Ctrl+C to stop)")
            time.sleep(POLL_INTERVAL_SECONDS)

    except KeyboardInterrupt:
        print("\nTrader stopped by user. Goodbye!")
        sys.exit(0)


if __name__ == "__main__":
    main()
