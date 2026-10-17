# Delta Exchange Automated Trading System

A modular, safety-first algorithmic trading bot designed for **Delta Exchange** (Crypto Perpetuals, Tokenized Stocks, and Futures), featuring a zero-risk **Paper Trading Engine**, **ORB + MA200 Strategy**, and **Strict Risk Kernel**.

---

## 🚀 Key Features

1. **Zero-Risk Paper Trading (Enabled by default)**:
   - Match orders virtually against real-time live Delta Exchange mark prices and orderbooks.
   - Realistic fill simulation with slippage (0.05%) and exchange taker fees (0.05%).
   - Dynamic trailing stop and automatic breakeven at 1.0R.
   - Real-time PnL tracking and local SQLite trade ledger.
   - **No API key required for paper trading!** (Public ticker and candle endpoints work out of the box).

2. **Instruments Supported**:
   - **Crypto Perpetuals**: `BTCUSD`, `ETHUSD`, etc.
   - **Tokenized Stocks**: `AAPLXUSD` (Apple), `NVDAXUSD` (NVIDIA), `TSLAXUSD` (Tesla), `AMZNXUSD`, etc.

3. **Built-in Strategies**:
   - **ORB + 200 EMA**: Multi-timeframe breakout strategy with 200 EMA trend confirmation and ATR volatility stops.
   - **EMA 9/21 Trend Crossover**: Momentum trend following with dynamic risk-to-reward targets.

4. **Safety Risk Kernel**:
   - Hard daily loss limit (`DAILY_LOSS_LIMIT_USD = -$150`) halts execution.
   - Daily profit target (`DAILY_PROFIT_TARGET_USD = $300`) locks in gains.
   - Maximum position count and per-trade risk sizing.

---

## 🛠️ Quick Start

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Verify Connection & Live Market Quotes
```bash
python test_delta_connection.py
```

### 3. Start Paper Trading (One-Click)
```bash
run_paper.bat
# or
python run_trader.py
```

---

## ⚙️ Configuration (`.env`)

You can edit `.env` to configure your settings:

```ini
# Switch between 'paper' and 'live'
TRADING_MODE=paper

# Exchange endpoint (India or Global)
DELTA_BASE_URL=https://api.india.delta.exchange

# Virtual Capital for Paper Trading
PAPER_INITIAL_CAPITAL=10000.0

# Watchlist symbols
WATCHLIST=BTCUSD,ETHUSD,AAPLXUSD,NVDAXUSD,TSLAXUSD

# Risk Limits
RISK_PER_TRADE_USD=50.0
DAILY_LOSS_LIMIT_USD=-150.0
DAILY_PROFIT_TARGET_USD=300.0
```

---

## 🔒 Going Live (When Ready)

1. Generate your API Key & Secret from your **Delta Exchange** account settings.
2. Add your credentials to `.env`:
   ```ini
   DELTA_API_KEY=your_key_here
   DELTA_API_SECRET=your_secret_here
   TRADING_MODE=live
   ```
3. Run `run_live.bat`.
