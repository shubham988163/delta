"""SQLite Ledger for logging Paper and Live trades, balances, and PnL.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from tabulate import tabulate

from trading.config import DB_PATH


class Ledger:
    """Manages trade persistence, position tracking, and historical stats."""

    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._get_conn() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS trades (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    trade_id TEXT UNIQUE,
                    timestamp TEXT,
                    symbol TEXT,
                    side TEXT,
                    contracts INTEGER,
                    entry_price REAL,
                    exit_price REAL,
                    stop_loss REAL,
                    take_profit REAL,
                    status TEXT,
                    realized_pnl REAL DEFAULT 0.0,
                    fees REAL DEFAULT 0.0,
                    slippage REAL DEFAULT 0.0,
                    exit_reason TEXT,
                    mode TEXT,
                    created_at TEXT,
                    closed_at TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS daily_balance (
                    date TEXT PRIMARY KEY,
                    start_balance REAL,
                    current_balance REAL,
                    realized_pnl REAL,
                    updated_at TEXT
                )
                """
            )
            conn.commit()

    def record_entry(
        self,
        trade_id: str,
        symbol: str,
        side: str,
        contracts: int,
        entry_price: float,
        stop_loss: float,
        take_profit: float,
        fees: float,
        slippage: float,
        mode: str,
    ) -> None:
        """Record trade opening."""
        now_str = datetime.now(timezone.utc).isoformat()
        with self._get_conn() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO trades 
                (trade_id, timestamp, symbol, side, contracts, entry_price, stop_loss, take_profit, 
                 status, fees, slippage, mode, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'OPEN', ?, ?, ?, ?)
                """,
                (
                    trade_id,
                    now_str,
                    symbol,
                    side.upper(),
                    contracts,
                    entry_price,
                    stop_loss,
                    take_profit,
                    fees,
                    slippage,
                    mode,
                    now_str,
                ),
            )
            conn.commit()

    def record_exit(
        self,
        trade_id: str,
        exit_price: float,
        realized_pnl: float,
        exit_reason: str,
        add_fees: float = 0.0,
    ) -> None:
        """Record trade closing."""
        now_str = datetime.now(timezone.utc).isoformat()
        with self._get_conn() as conn:
            conn.execute(
                """
                UPDATE trades 
                SET exit_price = ?, realized_pnl = ?, status = 'CLOSED', 
                    exit_reason = ?, fees = fees + ?, closed_at = ?
                WHERE trade_id = ?
                """,
                (exit_price, realized_pnl, exit_reason, add_fees, now_str, trade_id),
            )
            conn.commit()

    def get_open_trades(self, mode: str) -> List[Dict[str, Any]]:
        """Get currently open trades."""
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM trades WHERE status = 'OPEN' AND mode = ?", (mode,)
            ).fetchall()
            return [dict(r) for r in rows]

    def get_today_pnl(self, mode: str) -> float:
        """Get cumulative realized PnL for today in UTC."""
        today_prefix = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        with self._get_conn() as conn:
            row = conn.execute(
                """
                SELECT COALESCE(SUM(realized_pnl - fees), 0.0) as net_pnl
                FROM trades
                WHERE status = 'CLOSED' AND mode = ? AND timestamp LIKE ?
                """,
                (mode, f"{today_prefix}%"),
            ).fetchone()
            return float(row["net_pnl"]) if row else 0.0

    def get_trade_count_today(self, mode: str) -> int:
        """Get number of trades executed today."""
        today_prefix = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT COUNT(*) as count FROM trades WHERE mode = ? AND timestamp LIKE ?",
                (mode, f"{today_prefix}%"),
            ).fetchone()
            return int(row["count"]) if row else 0

    def print_recent_trades(self, limit: int = 5) -> None:
        """Print recent trades in a clean CLI table."""
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT trade_id, symbol, side, contracts, entry_price, exit_price, realized_pnl, status, mode FROM trades ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
            if rows:
                print(tabulate([dict(r) for r in rows], headers="keys", tablefmt="simple"))
