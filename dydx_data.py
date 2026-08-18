"""Public dYdX v4 funding data adapter.

The adapter is read-only and is suitable for research and paper-candidate
scans. It does not contain order, account, or wallet functionality.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import requests

from funding_data import fetch_dydx_funding_history


BASE_URL = "https://indexer.dydx.trade/v4"
TIMEOUT_SECONDS = 20


def _market_payload(payload: Any) -> dict[str, dict[str, Any]]:
    """Extract the dYdX perpetual-market mapping from the public response."""
    if not isinstance(payload, dict) or not isinstance(payload.get("markets"), dict):
        raise ValueError("dYdX perpetualMarkets response missing markets mapping")
    return payload["markets"]


def fetch_markets() -> dict[str, dict[str, Any]]:
    """Fetch the public active/inactive perpetual-market metadata."""
    response = requests.get(f"{BASE_URL}/perpetualMarkets", timeout=TIMEOUT_SECONDS)
    response.raise_for_status()
    return _market_payload(response.json())


def fetch_current_funding(coin: str) -> dict[str, Any]:
    """Return the current dYdX next-hour funding snapshot for ``coin``."""
    ticker = f"{coin.upper()}-USD"
    markets = fetch_markets()
    market = markets.get(ticker)
    if not market:
        raise ValueError(f"dYdX market not found: {ticker}")
    if market.get("status") != "ACTIVE":
        raise ValueError(f"dYdX market is not active: {ticker}")
    rate = market.get("nextFundingRate")
    try:
        rate_float = float(rate)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"dYdX market has invalid nextFundingRate: {ticker}") from exc
    return {
        "coin": coin.upper(),
        "ticker": ticker,
        "funding": rate_float,
        "oracle_price": float(market["oraclePrice"]),
        "open_interest": float(market["openInterest"]),
        "observed_at": datetime.now(timezone.utc).isoformat(),
    }


def fetch_historical_funding(coin: str, days: int = 14):
    """Fetch historical hourly funding through the validated Indexer adapter."""
    return fetch_dydx_funding_history(coin, days=days)


def endpoint_health(coin: str = "BTC") -> dict[str, Any]:
    """Perform read-only endpoint checks and return structured health details."""
    markets = fetch_markets()
    current = fetch_current_funding(coin)
    history = fetch_historical_funding(coin, days=1)
    return {
        "markets_http_ok": True,
        "market_count": len(markets),
        "current": current,
        "historical_rows_1d": int(len(history)),
        "historical_http_ok": True,
    }


if __name__ == "__main__":
    import json

    print(json.dumps(endpoint_health(), indent=2))
