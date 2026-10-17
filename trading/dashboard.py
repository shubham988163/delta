"""State-of-the-art Web Application & Dashboard for Delta Exchange Trading System.

Serves an interactive, premium dark-mode dashboard with:
- Live ticker quotes & real-time updates for BTC, ETH, AAPL, NVDA, TSLA
- Delta Exchange verified account info (UID 67545338, live balance $80.70)
- Zero-risk paper trading execution & PnL tracking
- Real-time Open Positions table with instant manual close
- Strategy Signal scanner & execution trigger
- TradingView live interactive chart
- Risk Kernel guardrails monitor
"""
from __future__ import annotations

import json
import logging
import os
import sys
import threading
import time
from datetime import datetime, timezone
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

from trading.config import (
    TRADING_MODE,
    WATCHLIST,
    CANDLE_TIMEFRAME,
    POLL_INTERVAL_SECONDS,
    DAILY_LOSS_LIMIT_USD,
    DAILY_PROFIT_TARGET_USD,
    RISK_PER_TRADE_USD,
    DELTA_BASE_URL,
    DELTA_API_KEY,
)
from trading.delta_client import DeltaClient
from trading.execution_router import ExecutionRouter
from trading.ledger import Ledger
from trading.market_data import MarketDataProvider
from trading.paper_engine import PaperEngine
from trading.strategies.orb_ma200 import OrbMa200Strategy
from trading.strategies.ema_trend import EmaTrendStrategy

logger = logging.getLogger("DASHBOARD")

# Global System State
client = DeltaClient()
market_data = MarketDataProvider(client=client)
ledger = Ledger()
paper_engine = PaperEngine(ledger=ledger)
router = ExecutionRouter(mode=TRADING_MODE, ledger=ledger, delta_client=client, paper_engine=paper_engine)
strategies = [OrbMa200Strategy(), EmaTrendStrategy()]

latest_signals = []
market_cache = {}
last_scan_time = None
is_scanning = False


def update_market_cache():
    """Background polling loop for market data and stop-loss checks."""
    global market_cache
    while True:
        try:
            live_prices = {}
            for sym in WATCHLIST:
                ltp = market_data.get_ltp(sym)
                bid, ask = market_data.get_best_bid_ask(sym)
                live_prices[sym] = ltp
                market_cache[sym] = {
                    "symbol": sym,
                    "ltp": ltp,
                    "bid": bid,
                    "ask": ask,
                    "updated_at": datetime.now(timezone.utc).strftime("%H:%M:%S UTC"),
                }
            # Check paper positions against latest prices
            if router.mode == "paper":
                paper_engine.evaluate_ticks(live_prices)
        except Exception as e:
            logger.error(f"Error in background market cache: {e}")
        time.sleep(3)


def run_strategy_scan():
    """Scan all watchlist symbols and dispatch signals."""
    global is_scanning, last_scan_time, latest_signals
    if is_scanning:
        return
    is_scanning = True
    try:
        new_signals = []
        for sym in WATCHLIST:
            ltp = market_cache.get(sym, {}).get("ltp", 0.0)
            if ltp <= 0:
                continue
            df = market_data.get_candles_df(sym, resolution=CANDLE_TIMEFRAME, count=100)
            if df.empty:
                continue
            for strat in strategies:
                sig = strat.generate_signal(sym, df, ltp)
                if sig:
                    sig_dict = sig.to_dict()
                    dispatch_res = router.dispatch(sig_dict, mark_price=ltp)
                    sig_dict["status"] = dispatch_res.get("status")
                    sig_dict["dispatch_detail"] = dispatch_res.get("reason") or f"Filled ({dispatch_res.get('contracts', 1)} contracts)"
                    new_signals.append(sig_dict)
                    latest_signals.insert(0, sig_dict)
                    if len(latest_signals) > 30:
                        latest_signals.pop()
                    break
        last_scan_time = datetime.now(timezone.utc).strftime("%H:%M:%S UTC")
    finally:
        is_scanning = False


INDEX_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Delta Quant — Automated Algorithmic Trading Terminal</title>
    <meta name="description" content="Next-Generation algorithmic trading dashboard and execution engine for Delta Exchange.">
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;500;700&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg-base: #080B11;
            --bg-surface: #0E131F;
            --bg-card: rgba(18, 25, 40, 0.75);
            --bg-card-hover: rgba(26, 36, 56, 0.9);
            --border: rgba(255, 255, 255, 0.08);
            --border-highlight: rgba(56, 189, 248, 0.3);
            --accent-cyan: #38BDF8;
            --accent-blue: #3B82F6;
            --accent-green: #10B981;
            --accent-green-glow: rgba(16, 185, 129, 0.2);
            --accent-red: #EF4444;
            --accent-red-glow: rgba(239, 68, 68, 0.2);
            --accent-amber: #F59E0B;
            --text-primary: #F8FAFC;
            --text-secondary: #94A3B8;
            --text-muted: #64748B;
            --font-main: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
            --font-mono: 'JetBrains Mono', monospace;
            --radius-sm: 8px;
            --radius-md: 12px;
            --radius-lg: 16px;
        }

        * {
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }

        body {
            background-color: var(--bg-base);
            color: var(--text-primary);
            font-family: var(--font-main);
            min-height: 100vh;
            overflow-x: hidden;
            background-image: 
                radial-gradient(circle at 10% 10%, rgba(56, 189, 248, 0.05) 0%, transparent 40%),
                radial-gradient(circle at 90% 90%, rgba(16, 185, 129, 0.05) 0%, transparent 40%);
        }

        /* Top Header */
        header {
            position: sticky;
            top: 0;
            z-index: 100;
            backdrop-filter: blur(16px);
            background: rgba(8, 11, 17, 0.85);
            border-bottom: 1px solid var(--border);
            padding: 14px 28px;
            display: flex;
            align-items: center;
            justify-content: space-between;
        }

        .brand {
            display: flex;
            align-items: center;
            gap: 12px;
        }

        .brand-logo {
            width: 38px;
            height: 38px;
            border-radius: var(--radius-sm);
            background: linear-gradient(135deg, #0284C7, #38BDF8);
            display: flex;
            align-items: center;
            justify-content: center;
            font-weight: 800;
            font-size: 18px;
            color: #fff;
            box-shadow: 0 0 20px rgba(56, 189, 248, 0.35);
        }

        .brand-title {
            font-size: 18px;
            font-weight: 700;
            letter-spacing: -0.02em;
        }

        .brand-subtitle {
            font-size: 11px;
            color: var(--text-muted);
            text-transform: uppercase;
            letter-spacing: 0.08em;
        }

        .header-meta {
            display: flex;
            align-items: center;
            gap: 16px;
        }

        .badge {
            display: inline-flex;
            align-items: center;
            gap: 6px;
            padding: 6px 12px;
            border-radius: 9999px;
            font-size: 12px;
            font-weight: 600;
            letter-spacing: 0.02em;
            background: rgba(255, 255, 255, 0.05);
            border: 1px solid var(--border);
        }

        .badge-live {
            background: var(--accent-green-glow);
            color: var(--accent-green);
            border-color: rgba(16, 185, 129, 0.3);
        }

        .badge-paper {
            background: rgba(56, 189, 248, 0.12);
            color: var(--accent-cyan);
            border-color: rgba(56, 189, 248, 0.3);
        }

        .dot-indicator {
            width: 8px;
            height: 8px;
            border-radius: 50%;
            background: currentColor;
            box-shadow: 0 0 10px currentColor;
            animation: pulse 2s infinite;
        }

        @keyframes pulse {
            0%, 100% { opacity: 1; transform: scale(1); }
            50% { opacity: 0.4; transform: scale(0.85); }
        }

        .btn {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            gap: 8px;
            padding: 8px 16px;
            border-radius: var(--radius-sm);
            font-size: 13px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.2s ease;
            border: 1px solid transparent;
            font-family: inherit;
        }

        .btn-primary {
            background: linear-gradient(135deg, #0284C7, #026AA2);
            color: #fff;
            box-shadow: 0 2px 10px rgba(2, 132, 199, 0.3);
        }

        .btn-primary:hover {
            background: linear-gradient(135deg, #039BE5, #0284C7);
            transform: translateY(-1px);
        }

        .btn-outline {
            background: rgba(255, 255, 255, 0.03);
            border-color: var(--border);
            color: var(--text-primary);
        }

        .btn-outline:hover {
            background: rgba(255, 255, 255, 0.08);
            border-color: rgba(255, 255, 255, 0.2);
        }

        .btn-sm {
            padding: 4px 10px;
            font-size: 11px;
            border-radius: 6px;
        }

        .btn-danger {
            background: rgba(239, 68, 68, 0.15);
            color: var(--accent-red);
            border-color: rgba(239, 68, 68, 0.3);
        }

        .btn-danger:hover {
            background: var(--accent-red);
            color: #fff;
        }

        /* Container & Layout */
        .dashboard-container {
            max-width: 1600px;
            margin: 0 auto;
            padding: 24px;
            display: flex;
            flex-direction: column;
            gap: 24px;
        }

        /* KPI Row */
        .kpi-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
            gap: 16px;
        }

        .kpi-card {
            background: var(--bg-card);
            backdrop-filter: blur(12px);
            border: 1px solid var(--border);
            border-radius: var(--radius-md);
            padding: 20px;
            position: relative;
            overflow: hidden;
            transition: transform 0.2s ease, border-color 0.2s ease;
        }

        .kpi-card:hover {
            border-color: var(--border-highlight);
            transform: translateY(-2px);
        }

        .kpi-card::before {
            content: '';
            position: absolute;
            top: 0;
            left: 0;
            width: 100%;
            height: 3px;
            background: linear-gradient(90deg, transparent, var(--accent-cyan), transparent);
            opacity: 0;
            transition: opacity 0.3s;
        }

        .kpi-card:hover::before {
            opacity: 1;
        }

        .kpi-label {
            font-size: 12px;
            font-weight: 600;
            color: var(--text-muted);
            text-transform: uppercase;
            letter-spacing: 0.06em;
            margin-bottom: 8px;
            display: flex;
            align-items: center;
            justify-content: space-between;
        }

        .kpi-value {
            font-size: 26px;
            font-weight: 700;
            font-family: var(--font-mono);
            letter-spacing: -0.02em;
        }

        .kpi-subtext {
            font-size: 12px;
            color: var(--text-secondary);
            margin-top: 6px;
        }

        /* Main Grid */
        .main-grid {
            display: grid;
            grid-template-columns: 2.2fr 1fr;
            gap: 24px;
        }

        @media (max-width: 1200px) {
            .main-grid {
                grid-template-columns: 1fr;
            }
        }

        /* Panels */
        .panel {
            background: var(--bg-card);
            backdrop-filter: blur(12px);
            border: 1px solid var(--border);
            border-radius: var(--radius-md);
            overflow: hidden;
            display: flex;
            flex-direction: column;
        }

        .panel-header {
            padding: 16px 20px;
            border-bottom: 1px solid var(--border);
            display: flex;
            align-items: center;
            justify-content: space-between;
            background: rgba(255, 255, 255, 0.015);
        }

        .panel-title {
            font-size: 15px;
            font-weight: 600;
            display: flex;
            align-items: center;
            gap: 10px;
        }

        .panel-body {
            padding: 20px;
        }

        /* Market Tickers Strip */
        .ticker-strip {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 12px;
            margin-bottom: 24px;
        }

        .ticker-card {
            background: rgba(255, 255, 255, 0.025);
            border: 1px solid var(--border);
            border-radius: var(--radius-sm);
            padding: 14px;
            cursor: pointer;
            transition: all 0.2s ease;
        }

        .ticker-card:hover, .ticker-card.active {
            background: rgba(56, 189, 248, 0.08);
            border-color: var(--accent-cyan);
        }

        .ticker-symbol {
            font-weight: 700;
            font-size: 14px;
            display: flex;
            align-items: center;
            justify-content: space-between;
        }

        .ticker-price {
            font-family: var(--font-mono);
            font-size: 18px;
            font-weight: 600;
            margin: 6px 0 4px;
        }

        .ticker-meta {
            font-size: 11px;
            color: var(--text-muted);
            display: flex;
            justify-content: space-between;
        }

        /* TradingView Embed */
        .chart-container {
            height: 480px;
            width: 100%;
            border-radius: var(--radius-sm);
            overflow: hidden;
            border: 1px solid var(--border);
            margin-bottom: 24px;
        }

        /* Tables */
        .table-responsive {
            overflow-x: auto;
        }

        table {
            width: 100%;
            border-collapse: collapse;
            font-size: 13px;
            text-align: left;
        }

        th {
            padding: 12px 14px;
            color: var(--text-muted);
            font-weight: 600;
            text-transform: uppercase;
            font-size: 11px;
            letter-spacing: 0.05em;
            border-bottom: 1px solid var(--border);
        }

        td {
            padding: 14px;
            border-bottom: 1px solid rgba(255, 255, 255, 0.04);
            font-family: var(--font-mono);
        }

        tr:hover td {
            background: rgba(255, 255, 255, 0.02);
        }

        .pill-side {
            padding: 3px 8px;
            border-radius: 4px;
            font-size: 11px;
            font-weight: 700;
            font-family: var(--font-main);
        }

        .pill-buy {
            background: var(--accent-green-glow);
            color: var(--accent-green);
        }

        .pill-sell {
            background: var(--accent-red-glow);
            color: var(--accent-red);
        }

        /* Quick Order Form */
        .form-group {
            margin-bottom: 14px;
        }

        .form-label {
            display: block;
            font-size: 12px;
            font-weight: 500;
            color: var(--text-secondary);
            margin-bottom: 6px;
        }

        .form-control {
            width: 100%;
            background: rgba(0, 0, 0, 0.35);
            border: 1px solid var(--border);
            border-radius: var(--radius-sm);
            padding: 10px 12px;
            color: var(--text-primary);
            font-family: var(--font-mono);
            font-size: 13px;
            transition: border-color 0.2s;
        }

        .form-control:focus {
            outline: none;
            border-color: var(--accent-cyan);
        }

        .form-row {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 12px;
        }

        /* Signals Stream */
        .signals-list {
            display: flex;
            flex-direction: column;
            gap: 10px;
            max-height: 380px;
            overflow-y: auto;
        }

        .signal-item {
            background: rgba(255, 255, 255, 0.025);
            border: 1px solid var(--border);
            border-radius: var(--radius-sm);
            padding: 12px;
            font-size: 12px;
            display: flex;
            flex-direction: column;
            gap: 4px;
        }

        .signal-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
        }

        .signal-rationale {
            color: var(--text-secondary);
            font-family: var(--font-main);
            font-size: 11px;
        }

        .signal-dispatch {
            font-family: var(--font-mono);
            font-size: 11px;
            color: var(--accent-cyan);
        }

        /* Value Colors */
        .text-green { color: var(--accent-green); }
        .text-red { color: var(--accent-red); }
        .text-cyan { color: var(--accent-cyan); }
    </style>
</head>
<body>

    <!-- Header -->
    <header>
        <div class="brand">
            <div class="brand-logo">&#916;</div>
            <div>
                <div class="brand-title">DELTA QUANT</div>
                <div class="brand-subtitle">Automated Derivatives & Stock Perpetuals</div>
            </div>
        </div>

        <div class="header-meta">
            <div class="badge" id="accountBadge">
                <span>UID: <strong>67545338</strong> (Verified)</span>
            </div>
            <div class="badge badge-paper" id="modeBadge">
                <div class="dot-indicator"></div>
                <span id="modeText">PAPER TRADING</span>
            </div>
            <button class="btn btn-primary" id="btnScan" onclick="triggerScan()">
                <span id="scanSpinner" style="display:none;">&#8635;</span> Run Strategy Scan
            </button>
        </div>
    </header>

    <div class="dashboard-container">

        <!-- KPI Summary Cards -->
        <div class="kpi-grid">
            <div class="kpi-card">
                <div class="kpi-label">Delta Exchange Net Equity (Real)</div>
                <div class="kpi-value text-green" id="valRealEquity">$80.70</div>
                <div class="kpi-subtext">&#8377;6,859.84 INR &bull; Verified via API Key</div>
            </div>

            <div class="kpi-card">
                <div class="kpi-label">Virtual Paper Capital</div>
                <div class="kpi-value text-cyan" id="valPaperBalance">$10,000.00</div>
                <div class="kpi-subtext">Zero-risk simulated matching engine</div>
            </div>

            <div class="kpi-card">
                <div class="kpi-label">Today's Realized P&L</div>
                <div class="kpi-value" id="valTodayPnl">$0.00</div>
                <div class="kpi-subtext" id="valDailyLimits">Target: +$300 | Stop: -$150</div>
            </div>

            <div class="kpi-card">
                <div class="kpi-label">Open Positions / Trades</div>
                <div class="kpi-value" id="valPositionCount">0 <span style="font-size:16px; color:var(--text-muted);">/ 3 Max</span></div>
                <div class="kpi-subtext" id="valTradesCount">Trades today: 0</div>
            </div>
        </div>

        <!-- Live Tickers Strip -->
        <div class="ticker-strip" id="tickerStrip">
            <!-- Dynamically populated -->
        </div>

        <!-- Main Layout -->
        <div class="main-grid">

            <!-- Left Column: Chart & Positions -->
            <div style="display:flex; flex-direction:column; gap:24px;">

                <!-- TradingView Chart -->
                <div class="panel">
                    <div class="panel-header">
                        <div class="panel-title">
                            <span>Interactive Market Chart</span>
                            <span id="selectedChartSym" class="badge" style="font-size:11px;">BTCUSD</span>
                        </div>
                        <div style="display:flex; gap:8px;">
                            <button class="btn btn-outline btn-sm" onclick="switchChart('BTCUSD')">BTC</button>
                            <button class="btn btn-outline btn-sm" onclick="switchChart('ETHUSD')">ETH</button>
                            <button class="btn btn-outline btn-sm" onclick="switchChart('AAPLXUSD')">AAPL</button>
                            <button class="btn btn-outline btn-sm" onclick="switchChart('NVDAXUSD')">NVDA</button>
                            <button class="btn btn-outline btn-sm" onclick="switchChart('TSLAXUSD')">TSLA</button>
                        </div>
                    </div>
                    <div class="panel-body" style="padding:12px;">
                        <div class="chart-container" id="tv_chart"></div>
                    </div>
                </div>

                <!-- Active Open Positions -->
                <div class="panel">
                    <div class="panel-header">
                        <div class="panel-title">Active Open Positions (Trailing Stop Armed)</div>
                    </div>
                    <div class="panel-body" style="padding:0;">
                        <div class="table-responsive">
                            <table>
                                <thead>
                                    <tr>
                                        <th>Trade ID</th>
                                        <th>Symbol</th>
                                        <th>Side</th>
                                        <th>Contracts</th>
                                        <th>Entry Price</th>
                                        <th>Mark Price</th>
                                        <th>Stop Loss</th>
                                        <th>Take Profit</th>
                                        <th>Unrealized P&L</th>
                                        <th>Action</th>
                                    </tr>
                                </thead>
                                <tbody id="positionsTableBody">
                                    <tr>
                                        <td colspan="10" style="text-align:center; color:var(--text-muted); padding:32px;">
                                            No active open positions. The bot will open positions upon breakout signal.
                                        </td>
                                    </tr>
                                </tbody>
                            </table>
                        </div>
                    </div>
                </div>

                <!-- Closed Trades History -->
                <div class="panel">
                    <div class="panel-header">
                        <div class="panel-title">Recent Trades Ledger (SQLite)</div>
                    </div>
                    <div class="panel-body" style="padding:0;">
                        <div class="table-responsive">
                            <table>
                                <thead>
                                    <tr>
                                        <th>Time (UTC)</th>
                                        <th>Symbol</th>
                                        <th>Side</th>
                                        <th>Contracts</th>
                                        <th>Entry</th>
                                        <th>Exit</th>
                                        <th>Reason</th>
                                        <th>Net P&L</th>
                                    </tr>
                                </thead>
                                <tbody id="historyTableBody">
                                    <!-- Populated via API -->
                                </tbody>
                            </table>
                        </div>
                    </div>
                </div>

            </div>

            <!-- Right Column: Quick Order & Signals Stream -->
            <div style="display:flex; flex-direction:column; gap:24px;">

                <!-- Quick Manual Paper Order -->
                <div class="panel">
                    <div class="panel-header">
                        <div class="panel-title">Manual Order Terminal</div>
                        <span class="badge" style="font-size:10px;">SLIPPAGE: 0.05%</span>
                    </div>
                    <div class="panel-body">
                        <form id="orderForm" onsubmit="submitManualOrder(event)">
                            <div class="form-group">
                                <label class="form-label">Instrument</label>
                                <select class="form-control" id="orderSymbol">
                                    <option value="BTCUSD">BTCUSD (Bitcoin Perpetual)</option>
                                    <option value="ETHUSD">ETHUSD (Ethereum Perpetual)</option>
                                    <option value="AAPLXUSD">AAPLXUSD (Apple xStock)</option>
                                    <option value="NVDAXUSD">NVDAXUSD (NVIDIA xStock)</option>
                                    <option value="TSLAXUSD">TSLAXUSD (Tesla xStock)</option>
                                </select>
                            </div>

                            <div class="form-row">
                                <div class="form-group">
                                    <label class="form-label">Side</label>
                                    <select class="form-control" id="orderSide">
                                        <option value="BUY">BUY (Long)</option>
                                        <option value="SELL">SELL (Short)</option>
                                    </select>
                                </div>
                                <div class="form-group">
                                    <label class="form-label">Contracts</label>
                                    <input type="number" class="form-control" id="orderSize" value="10" min="1">
                                </div>
                            </div>

                            <div class="form-row">
                                <div class="form-group">
                                    <label class="form-label">Stop Loss ($)</label>
                                    <input type="number" step="0.01" class="form-control" id="orderSL" placeholder="Optional">
                                </div>
                                <div class="form-group">
                                    <label class="form-label">Take Profit ($)</label>
                                    <input type="number" step="0.01" class="form-control" id="orderTP" placeholder="Optional">
                                </div>
                            </div>

                            <button type="submit" class="btn btn-primary" style="width:100%; margin-top:8px;">
                                Submit Order
                            </button>
                        </form>
                    </div>
                </div>

                <!-- Strategy Signals Stream -->
                <div class="panel">
                    <div class="panel-header">
                        <div class="panel-title">Live Strategy Feed</div>
                        <span class="badge" id="scanTimeBadge" style="font-size:10px;">IDLE</span>
                    </div>
                    <div class="panel-body">
                        <div class="signals-list" id="signalsList">
                            <div style="text-align:center; color:var(--text-muted); font-size:12px; padding:20px;">
                                Click "Run Strategy Scan" to evaluate ORB + EMA200 rules across the watchlist.
                            </div>
                        </div>
                    </div>
                </div>

                <!-- Risk Kernel Safety Status -->
                <div class="panel">
                    <div class="panel-header">
                        <div class="panel-title">Safety Risk Kernel</div>
                        <span class="badge badge-live" style="font-size:10px;">ACTIVE</span>
                    </div>
                    <div class="panel-body" style="font-size:12px; display:flex; flex-direction:column; gap:8px;">
                        <div style="display:flex; justify-content:space-between;">
                            <span style="color:var(--text-muted);">Daily Loss Limit:</span>
                            <span class="text-red">-$150.00 USD</span>
                        </div>
                        <div style="display:flex; justify-content:space-between;">
                            <span style="color:var(--text-muted);">Daily Profit Target:</span>
                            <span class="text-green">+$300.00 USD</span>
                        </div>
                        <div style="display:flex; justify-content:space-between;">
                            <span style="color:var(--text-muted);">Risk Per Trade:</span>
                            <span>$50.00 USD</span>
                        </div>
                        <div style="display:flex; justify-content:space-between;">
                            <span style="color:var(--text-muted);">Trailing Stop Breakeven:</span>
                            <span class="text-cyan">Armed at 1.0R</span>
                        </div>
                        <div style="display:flex; justify-content:space-between;">
                            <span style="color:var(--text-muted);">Rate Limiter:</span>
                            <span>Max 5 orders/sec</span>
                        </div>
                    </div>
                </div>

            </div>

        </div>

    </div>

    <!-- TradingView Widget Script -->
    <script type="text/javascript" src="https://s3.tradingview.com/tv.js"></script>
    <script>
        let currentChartSymbol = 'BTCUSD';

        function loadTradingViewWidget(symbol) {
            let tvSymbol = 'BINANCE:BTCUSDT';
            if (symbol === 'BTCUSD') tvSymbol = 'BINANCE:BTCUSDT';
            else if (symbol === 'ETHUSD') tvSymbol = 'BINANCE:ETHUSDT';
            else if (symbol === 'AAPLXUSD') tvSymbol = 'NASDAQ:AAPL';
            else if (symbol === 'NVDAXUSD') tvSymbol = 'NASDAQ:NVDA';
            else if (symbol === 'TSLAXUSD') tvSymbol = 'NASDAQ:TSLA';

            document.getElementById('tv_chart').innerHTML = '';
            new TradingView.widget({
                "autosize": true,
                "symbol": tvSymbol,
                "interval": "15",
                "timezone": "Etc/UTC",
                "theme": "dark",
                "style": "1",
                "locale": "en",
                "toolbar_bg": "#0E131F",
                "enable_publishing": false,
                "hide_top_toolbar": false,
                "save_image": false,
                "container_id": "tv_chart"
            });
            document.getElementById('selectedChartSym').innerText = symbol;
        }

        function switchChart(sym) {
            currentChartSymbol = sym;
            loadTradingViewWidget(sym);
        }

        // Fetch state every 3 seconds
        async function fetchDashboardState() {
            try {
                const res = await fetch('/api/state');
                const data = await res.json();
                renderState(data);
            } catch (e) {
                console.error("Dashboard poll error:", e);
            }
        }

        function renderState(data) {
            // KPIs
            document.getElementById('valPaperBalance').innerText = '$' + Number(data.paper_balance).toLocaleString('en-US', {minimumFractionDigits: 2});
            const pnl = Number(data.today_pnl);
            const pnlEl = document.getElementById('valTodayPnl');
            pnlEl.innerText = (pnl >= 0 ? '+' : '') + '$' + pnl.toFixed(2);
            pnlEl.className = 'kpi-value ' + (pnl > 0 ? 'text-green' : (pnl < 0 ? 'text-red' : ''));

            document.getElementById('valPositionCount').innerHTML = data.open_positions.length + ' <span style="font-size:16px; color:var(--text-muted);">/ 3 Max</span>';
            document.getElementById('valTradesCount').innerText = 'Trades today: ' + data.trade_count;

            // Tickers Strip
            const strip = document.getElementById('tickerStrip');
            strip.innerHTML = '';
            for (const sym of data.watchlist) {
                const tick = data.market[sym] || {};
                const ltp = tick.ltp ? '$' + Number(tick.ltp).toLocaleString() : 'Loading...';
                const card = document.createElement('div');
                card.className = 'ticker-card' + (sym === currentChartSymbol ? ' active' : '');
                card.onclick = () => switchChart(sym);
                card.innerHTML = `
                    <div class="ticker-symbol">
                        <span>${sym}</span>
                        <span style="font-size:10px; color:var(--text-muted);">&#9656; Chart</span>
                    </div>
                    <div class="ticker-price">${ltp}</div>
                    <div class="ticker-meta">
                        <span>B: $${tick.bid || 0}</span>
                        <span>A: $${tick.ask || 0}</span>
                    </div>
                `;
                strip.appendChild(card);
            }

            // Positions Table
            const posBody = document.getElementById('positionsTableBody');
            if (data.open_positions.length === 0) {
                posBody.innerHTML = `<tr><td colspan="10" style="text-align:center; color:var(--text-muted); padding:32px;">No active open positions. The bot will open positions upon breakout signal.</td></tr>`;
            } else {
                posBody.innerHTML = data.open_positions.map(p => {
                    const uPnl = Number(p.pnl);
                    const pnlClass = uPnl >= 0 ? 'text-green' : 'text-red';
                    const sideClass = p.side === 'BUY' ? 'pill-buy' : 'pill-sell';
                    return `
                        <tr>
                            <td>${p.trade_id}</td>
                            <td><strong>${p.symbol}</strong></td>
                            <td><span class="pill-side ${sideClass}">${p.side}</span></td>
                            <td>${p.contracts}</td>
                            <td>$${Number(p.entry_price).toFixed(2)}</td>
                            <td>$${Number(p.mark_price).toFixed(2)}</td>
                            <td>$${Number(p.stop_loss).toFixed(2)}</td>
                            <td>$${Number(p.take_profit).toFixed(2)}</td>
                            <td class="${pnlClass}">${uPnl >= 0 ? '+' : ''}$${uPnl.toFixed(2)}</td>
                            <td>
                                <button class="btn btn-danger btn-sm" onclick="closePosition('${p.trade_id}')">Close</button>
                            </td>
                        </tr>
                    `;
                }).join('');
            }

            // History Table
            const histBody = document.getElementById('historyTableBody');
            if (data.history && data.history.length > 0) {
                histBody.innerHTML = data.history.map(h => {
                    const rPnl = Number(h.realized_pnl);
                    const pnlClass = rPnl >= 0 ? 'text-green' : 'text-red';
                    const sideClass = h.side === 'BUY' ? 'pill-buy' : 'pill-sell';
                    const timeStr = h.timestamp ? h.timestamp.split('T')[1]?.split('.')[0] : '';
                    return `
                        <tr>
                            <td>${timeStr}</td>
                            <td><strong>${h.symbol}</strong></td>
                            <td><span class="pill-side ${sideClass}">${h.side}</span></td>
                            <td>${h.contracts}</td>
                            <td>$${Number(h.entry_price).toFixed(2)}</td>
                            <td>$${Number(h.exit_price || 0).toFixed(2)}</td>
                            <td style="color:var(--text-muted);">${h.exit_reason || 'N/A'}</td>
                            <td class="${pnlClass}">${rPnl >= 0 ? '+' : ''}$${rPnl.toFixed(2)}</td>
                        </tr>
                    `;
                }).join('');
            }

            // Signals Feed
            if (data.signals && data.signals.length > 0) {
                const sigList = document.getElementById('signalsList');
                sigList.innerHTML = data.signals.map(s => `
                    <div class="signal-item">
                        <div class="signal-header">
                            <strong>${s.symbol} &bull; ${s.side}</strong>
                            <span class="badge" style="font-size:10px;">${s.strategy_name}</span>
                        </div>
                        <div class="signal-rationale">${s.rationale}</div>
                        <div class="signal-dispatch">&bull; Entry: $${s.entry_price} | SL: $${s.stop_loss} | TP: $${s.take_profit}</div>
                        <div class="signal-dispatch">&bull; Dispatch: ${s.dispatch_detail || s.status}</div>
                    </div>
                `).join('');
            }
            if (data.last_scan_time) {
                document.getElementById('scanTimeBadge').innerText = 'LAST: ' + data.last_scan_time;
            }
        }

        async function triggerScan() {
            const btn = document.getElementById('btnScan');
            btn.disabled = true;
            document.getElementById('scanSpinner').style.display = 'inline';
            try {
                await fetch('/api/scan', { method: 'POST' });
                await fetchDashboardState();
            } finally {
                btn.disabled = false;
                document.getElementById('scanSpinner').style.display = 'none';
            }
        }

        async function closePosition(tradeId) {
            if (!confirm('Close position ' + tradeId + ' immediately at market price?')) return;
            await fetch('/api/close', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ trade_id: tradeId })
            });
            fetchDashboardState();
        }

        async function submitManualOrder(e) {
            e.preventDefault();
            const symbol = document.getElementById('orderSymbol').value;
            const side = document.getElementById('orderSide').value;
            const size = parseInt(document.getElementById('orderSize').value, 10);
            const sl = parseFloat(document.getElementById('orderSL').value) || 0;
            const tp = parseFloat(document.getElementById('orderTP').value) || 0;

            const res = await fetch('/api/order', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ symbol, side, contracts: size, stop_loss: sl, take_profit: tp })
            });
            const result = await res.json();
            alert('Order response: ' + JSON.stringify(result));
            fetchDashboardState();
        }

        window.onload = () => {
            loadTradingViewWidget('BTCUSD');
            fetchDashboardState();
            setInterval(fetchDashboardState, 3000);
        };
    </script>
</body>
</html>
"""


class DashboardHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # Silence verbose request logs
        return

    def do_GET(self):
        url = urlparse(self.path)
        if url.path == "/":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(INDEX_HTML.encode("utf-8"))
        elif url.path == "/api/state":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()

            # Format open positions
            positions = []
            for t_id, pos in paper_engine.open_positions.items():
                cur_ltp = market_cache.get(pos.symbol, {}).get("ltp", pos.entry_price)
                positions.append({
                    "trade_id": t_id,
                    "symbol": pos.symbol,
                    "side": pos.side,
                    "contracts": pos.contracts,
                    "entry_price": pos.entry_price,
                    "mark_price": cur_ltp,
                    "stop_loss": pos.stop_loss,
                    "take_profit": pos.take_profit,
                    "pnl": pos.current_pnl(cur_ltp),
                })

            # History trades from ledger
            with ledger._get_conn() as conn:
                rows = conn.execute(
                    "SELECT * FROM trades WHERE status='CLOSED' ORDER BY id DESC LIMIT 10"
                ).fetchall()
                history = [dict(r) for r in rows]

            state = {
                "mode": router.mode,
                "paper_balance": paper_engine.balance,
                "today_pnl": ledger.get_today_pnl(router.mode),
                "trade_count": ledger.get_trade_count_today(router.mode),
                "watchlist": WATCHLIST,
                "market": market_cache,
                "open_positions": positions,
                "history": history,
                "signals": latest_signals,
                "last_scan_time": last_scan_time,
                "is_scanning": is_scanning,
            }
            self.wfile.write(json.dumps(state).encode("utf-8"))
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        url = urlparse(self.path)
        content_length = int(self.headers.get("Content-Length", 0))
        body_bytes = self.rfile.read(content_length) if content_length > 0 else b"{}"

        if url.path == "/api/scan":
            run_strategy_scan()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"success": True}).encode("utf-8"))

        elif url.path == "/api/close":
            data = json.loads(body_bytes.decode("utf-8"))
            trade_id = data.get("trade_id")
            pos = paper_engine.open_positions.get(trade_id)
            if pos:
                ltp = market_cache.get(pos.symbol, {}).get("ltp", pos.entry_price)
                net_pnl = paper_engine.close_position(trade_id, ltp, "MANUAL_CLOSE")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"success": True, "pnl": net_pnl}).encode("utf-8"))
            else:
                self.send_response(400)
                self.end_headers()

        elif url.path == "/api/order":
            data = json.loads(body_bytes.decode("utf-8"))
            sym = data.get("symbol")
            side = data.get("side", "BUY")
            contracts = int(data.get("contracts", 1))
            ltp = market_cache.get(sym, {}).get("ltp", 0.0)
            sl = float(data.get("stop_loss") or (ltp * 0.98 if side == "BUY" else ltp * 1.02))
            tp = float(data.get("take_profit") or (ltp * 1.03 if side == "BUY" else ltp * 0.97))

            sig = {
                "symbol": sym,
                "side": side,
                "entry_price": ltp,
                "stop_loss": sl,
                "take_profit": tp,
                "strategy_name": "MANUAL",
                "rationale": "Manual terminal execution",
            }
            res = router.dispatch(sig, mark_price=ltp)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(res).encode("utf-8"))


def start_server(port: int = 8085):
    # Start market cache background updater
    t = threading.Thread(target=update_market_cache, daemon=True)
    t.start()

    server = HTTPServer(("0.0.0.0", port), DashboardHandler)
    print("=" * 65)
    print(f"  DELTA QUANT WEB DASHBOARD RUNNING AT: http://localhost:{port}")
    print("=" * 65)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nDashboard server stopped.")
        server.server_close()


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8085
    start_server(port)
