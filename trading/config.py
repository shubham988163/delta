"""Central configuration for Delta Exchange trading bot.

Anchored to the project root with strict risk limits for both paper and live modes.
"""
from __future__ import annotations

import os
from pathlib import Path
from zoneinfo import ZoneInfo
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

# Timezones
UTC = ZoneInfo("UTC")
IST = ZoneInfo("Asia/Kolkata")

# Mode: 'paper' (default) or 'live'
TRADING_MODE = os.getenv("TRADING_MODE", "paper").lower()
assert TRADING_MODE in ("paper", "live"), f"Invalid TRADING_MODE: {TRADING_MODE}. Must be 'paper' or 'live'."

# Delta Exchange API Endpoints
DELTA_BASE_URL = os.getenv("DELTA_BASE_URL", "https://api.india.delta.exchange").rstrip("/")
DELTA_WS_URL = os.getenv("DELTA_WS_URL", "wss://socket.india.delta.exchange")

# Credentials
DELTA_API_KEY = os.getenv("DELTA_API_KEY", "").strip()
DELTA_API_SECRET = os.getenv("DELTA_API_SECRET", "").strip()

# Paper Trading Capital (Virtual USD / USDT balance)
PAPER_INITIAL_CAPITAL = float(os.getenv("PAPER_INITIAL_CAPITAL", 10000.0))

# Hard Risk Kernel Limits (Enforced strictly on both Paper & Live)
RISK_PER_TRADE_USD = float(os.getenv("RISK_PER_TRADE_USD", 50.0))
MAX_OPEN_POSITIONS = int(os.getenv("MAX_OPEN_POSITIONS", 3))
DAILY_LOSS_LIMIT_USD = float(os.getenv("DAILY_LOSS_LIMIT_USD", -150.0))
DAILY_PROFIT_TARGET_USD = float(os.getenv("DAILY_PROFIT_TARGET_USD", 300.0))
MAX_POSITION_VALUE_USD = float(os.getenv("MAX_POSITION_VALUE_USD", 2500.0))
MAX_ORDERS_PER_SEC = int(os.getenv("MAX_ORDERS_PER_SEC", 5))

# Friction & Fill Model (Paper simulation)
SLIPPAGE_PCT = float(os.getenv("SLIPPAGE_PCT", 0.0005))       # 0.05% slippage
TAKER_FEE_PCT = float(os.getenv("TAKER_FEE_PCT", 0.0005))     # 0.05% taker fee
MAKER_FEE_PCT = float(os.getenv("MAKER_FEE_PCT", 0.0002))     # 0.02% maker fee

# Watchlist: Crypto & Tokenized Stocks
raw_watchlist = os.getenv("WATCHLIST", "BTCUSD,ETHUSD,AAPLXUSD,NVDAXUSD,TSLAXUSD")
WATCHLIST = [s.strip().upper() for s in raw_watchlist.split(",") if s.strip()]

# Strategy Defaults
CANDLE_TIMEFRAME = os.getenv("CANDLE_TIMEFRAME", "15m")
FAST_EMA = int(os.getenv("FAST_EMA", 9))
SLOW_EMA = int(os.getenv("SLOW_EMA", 21))
TREND_EMA = int(os.getenv("TREND_EMA", 200))
RR_TARGET = float(os.getenv("RR_RATIO", 1.5))
TRAILING_STOP_ENABLED = os.getenv("TRAILING_STOP_ENABLED", "True").lower() == "true"
BREAKEVEN_AT_R = float(os.getenv("BREAKEVEN_AT_R", 1.0))
POLL_INTERVAL_SECONDS = int(os.getenv("POLL_INTERVAL_SECONDS", 30))

# Paths
DATA_DIR = PROJECT_ROOT / "data"
LOGS_DIR = PROJECT_ROOT / "logs"
DB_PATH = DATA_DIR / "ledger.db"
TODAY_CONFIG_PATH = DATA_DIR / "today_config.json"
