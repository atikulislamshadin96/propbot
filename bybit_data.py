import requests

BASE = "https://api.bybit.com"

def bybit_funding_current(symbol="BTCUSDT"):
    r = requests.get(f"{BASE}/v5/market/tickers",
                     params={"category": "linear", "symbol": symbol}, timeout=10)
    r.raise_for_status()
    return float(r.json()["result"]["list"][0]["fundingRate"])

def bybit_funding_history(symbol="BTCUSDT", limit=200):
    r = requests.get(f"{BASE}/v5/market/funding/history",
                     params={"category": "linear", "symbol": symbol, "limit": limit},
                     timeout=10)
    r.raise_for_status()
    return [{"ts": int(x["fundingRateTimestamp"]), "rate": float(x["fundingRate"])}
            for x in r.json()["result"]["list"]]
