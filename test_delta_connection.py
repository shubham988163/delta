"""Verification script to test Delta Exchange API connectivity and quotes.
"""
from trading.delta_client import DeltaClient
from trading.market_data import MarketDataProvider
from trading.config import DELTA_BASE_URL, WATCHLIST

def test():
    print("Testing Delta Exchange API connection...")
    print(f"Base URL: {DELTA_BASE_URL}")
    client = DeltaClient()
    
    # 1. Test Products
    prods = client.get_products()
    print(f"Total Products available: {len(prods)}")
    
    # 2. Test Watchlist Tickers
    provider = MarketDataProvider(client=client)
    print("\nLive Watchlist Tickers:")
    for sym in WATCHLIST:
        ltp = provider.get_ltp(sym)
        bid, ask = provider.get_best_bid_ask(sym)
        print(f" - {sym:<10}: LTP = ${ltp:,.2f} | Bid = ${bid:,.2f} | Ask = ${ask:,.2f}")
        
    print("\nConnection & Market Data test successful!")

if __name__ == "__main__":
    test()
