"""Delta Exchange REST and WebSocket API client with HMAC-SHA256 authentication.

Provides complete functionality for fetching market data, products, tickers,
candles, and executing/managing orders.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time
from typing import Any, Dict, List, Optional
import requests

from trading.config import DELTA_BASE_URL, DELTA_API_KEY, DELTA_API_SECRET

logger = logging.getLogger(__name__)


class DeltaClient:
    """REST Client for Delta Exchange (India and Global)."""

    def __init__(
        self,
        base_url: str = DELTA_BASE_URL,
        api_key: str = DELTA_API_KEY,
        api_secret: str = DELTA_API_SECRET,
        timeout: int = 10,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.api_secret = api_secret
        self.timeout = timeout
        self.session = requests.Session()
        self._products_cache: Dict[str, Dict[str, Any]] = {}
        self._product_id_map: Dict[str, int] = {}

    def _generate_signature(
        self, method: str, timestamp: str, path: str, query_str: str = "", body_str: str = ""
    ) -> str:
        """Generate HMAC SHA256 signature for private endpoints."""
        message = method.upper() + timestamp + path + query_str + body_str
        return hmac.new(
            self.api_secret.encode("utf-8"), message.encode("utf-8"), hashlib.sha256
        ).hexdigest()

    def request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        payload: Optional[Dict[str, Any]] = None,
        auth_required: bool = False,
    ) -> Dict[str, Any]:
        """Send HTTP request to Delta Exchange API."""
        url = self.base_url + endpoint
        headers = {"Content-Type": "application/json"}

        # Format query parameters
        query_str = ""
        if params:
            # Sort params for deterministic signing if authenticated
            sorted_params = sorted(params.items())
            query_str = "?" + "&".join(f"{k}={v}" for k, v in sorted_params if v is not None)

        body_str = json.dumps(payload) if payload else ""

        if auth_required:
            if not self.api_key or not self.api_secret:
                raise ValueError("API Key and Secret are required for private endpoints.")
            timestamp = str(int(time.time()))
            signature = self._generate_signature(
                method=method,
                timestamp=timestamp,
                path=endpoint,
                query_str=query_str,
                body_str=body_str,
            )
            headers["api-key"] = self.api_key
            headers["timestamp"] = timestamp
            headers["signature"] = signature

        try:
            req_url = url + query_str
            resp = self.session.request(
                method=method.upper(),
                url=req_url,
                headers=headers,
                data=body_str if body_str else None,
                timeout=self.timeout,
            )
            if resp.status_code >= 400:
                logger.error(f"Delta API error [{resp.status_code}] on {endpoint}: {resp.text}")
                return {"success": False, "error": resp.text, "status_code": resp.status_code}
            return resp.json()
        except Exception as e:
            logger.error(f"Request exception on {endpoint}: {e}")
            return {"success": False, "error": str(e)}

    # --- Public Market Data Endpoints (No API Key Required) ---

    def get_products(self, refresh: bool = False) -> Dict[str, Dict[str, Any]]:
        """Fetch all products (perpetuals, futures, options, tokenized stocks)."""
        if self._products_cache and not refresh:
            return self._products_cache

        data = self.request("GET", "/v2/products")
        if data.get("success"):
            for p in data.get("result", []):
                sym = p.get("symbol")
                if sym:
                    self._products_cache[sym] = p
                    self._product_id_map[sym] = p.get("id")
        return self._products_cache

    def get_product(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Get product metadata by symbol."""
        if not self._products_cache:
            self.get_products()
        return self._products_cache.get(symbol.upper())

    def get_product_id(self, symbol: str) -> Optional[int]:
        """Get Delta numeric product_id for a symbol."""
        prod = self.get_product(symbol)
        return prod.get("id") if prod else None

    def get_ticker(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Get live ticker quote for a symbol."""
        endpoint = f"/v2/tickers/{symbol.upper()}"
        data = self.request("GET", endpoint)
        if data.get("success"):
            return data.get("result", {})
        return None

    def get_all_tickers(self) -> List[Dict[str, Any]]:
        """Fetch all live tickers."""
        data = self.request("GET", "/v2/tickers")
        if data.get("success"):
            return data.get("result", [])
        return []

    def get_candles(
        self, symbol: str, resolution: str = "15m", start: Optional[int] = None, end: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """Fetch OHLCV historical candles.
        
        Allowed resolutions: 1m, 3m, 5m, 15m, 30m, 1h, 2h, 4h, 6h, 1d, 1w.
        """
        now = int(time.time())
        if end is None:
            end = now
        if start is None:
            start = end - (86400 * 3)  # default 3 days

        params = {"symbol": symbol.upper(), "resolution": resolution, "start": start, "end": end}
        data = self.request("GET", "/v2/history/candles", params=params)
        if data.get("success"):
            return data.get("result", [])
        return []

    def get_orderbook(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Fetch L2 orderbook for a symbol."""
        endpoint = f"/v2/l2orderbook/{symbol.upper()}"
        data = self.request("GET", endpoint)
        if data.get("success"):
            return data.get("result", {})
        return None

    # --- Authenticated Endpoints (Requires API Key & Secret) ---

    def get_wallet_balances(self) -> List[Dict[str, Any]]:
        """Fetch account wallet balances (USDT, USD, etc.)."""
        data = self.request("GET", "/v2/wallet/balances", auth_required=True)
        if data.get("success"):
            return data.get("result", [])
        return []

    def get_positions(self) -> List[Dict[str, Any]]:
        """Fetch open derivative positions."""
        data = self.request("GET", "/v2/positions", auth_required=True)
        if data.get("success"):
            return data.get("result", [])
        return []

    def place_order(
        self,
        product_id: int,
        size: int,
        side: str,
        order_type: str = "market_order",
        limit_price: Optional[str] = None,
        stop_price: Optional[str] = None,
        time_in_force: str = "gtc",
    ) -> Dict[str, Any]:
        """Place an order on Delta Exchange.
        
        Args:
            product_id: Numeric Delta product ID.
            size: Number of contracts (integer).
            side: 'buy' or 'sell'.
            order_type: 'market_order', 'limit_order', etc.
            limit_price: String representation of limit price.
            stop_price: Trigger price for stop orders.
            time_in_force: 'gtc', 'ioc', 'fok'.
        """
        payload: Dict[str, Any] = {
            "product_id": product_id,
            "size": int(size),
            "side": side.lower(),
            "order_type": order_type,
            "time_in_force": time_in_force,
        }
        if limit_price:
            payload["limit_price"] = str(limit_price)
        if stop_price:
            payload["stop_price"] = str(stop_price)

        return self.request("POST", "/v2/orders", payload=payload, auth_required=True)

    def cancel_order(self, product_id: int, order_id: str) -> Dict[str, Any]:
        """Cancel an open order."""
        payload = {"product_id": product_id, "id": str(order_id)}
        return self.request("DELETE", "/v2/orders", payload=payload, auth_required=True)
