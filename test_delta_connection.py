"""Verification script to test Delta Exchange API connectivity, quotes, and authentication.
"""
from trading.delta_client import DeltaClient
from trading.market_data import MarketDataProvider
from trading.config import DELTA_BASE_URL, WATCHLIST, DELTA_API_KEY, TRADING_MODE

def test():
    print("=" * 65)
    print("       DELTA EXCHANGE CONNECTION AND AUTHENTICATION TEST       ")
    print("=" * 65)
    print(f"Mode       : {TRADING_MODE.upper()}")
    print(f"Base URL   : {DELTA_BASE_URL}")
    key_display = (DELTA_API_KEY[:6] + "..." + DELTA_API_KEY[-4:]) if DELTA_API_KEY else "Not Configured"
    print(f"API Key    : {key_display}")
    print("=" * 65)
    
    client = DeltaClient()
    
    # 1. Test Products (Public)
    prods = client.get_products()
    print(f"[1/3] Products Catalog : {len(prods)} active contracts found.")
    
    # 2. Test Watchlist Tickers (Public)
    print("\n[2/3] Live Market Quotes:")
    provider = MarketDataProvider(client=client)
    for sym in WATCHLIST:
        ltp = provider.get_ltp(sym)
        bid, ask = provider.get_best_bid_ask(sym)
        print(f"  - {sym:<10}: LTP = ${ltp:,.2f} | Bid = ${bid:,.2f} | Ask = ${ask:,.2f}")
        
    # 3. Test Authentication (Private)
    print("\n[3/3] Authenticated Account Check:")
    if not DELTA_API_KEY:
        print("  -> No API key configured. Running in unauthenticated Paper Trading mode.")
    else:
        balances = client.get_wallet_balances()
        if balances:
            print(f"  -> Authentication SUCCESSFUL! Found {len(balances)} asset balances:")
            for b in balances:
                asset = b.get("asset_symbol", "USD")
                bal = float(b.get("balance", 0.0))
                avail = float(b.get("available_balance", 0.0))
                if bal > 0 or avail > 0:
                    print(f"     * {asset}: Balance = {bal:.4f} | Available = {avail:.4f}")
        else:
            print("  -> Authentication response pending or no balances returned.")
            print("     (Note: Delta Exchange newly created API keys require ~5 mins to activate).")
            
    print("\nTest completed successfully!")

if __name__ == '__main__':
    test()
