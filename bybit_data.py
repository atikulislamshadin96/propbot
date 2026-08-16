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

def bybit_open_interest_history(symbol="BTCUSDT", limit=9):
    r = requests.get(f"{BASE}/v5/market/open-interest",
                     params={"category": "linear", "symbol": symbol,
                             "intervalTime": "1h", "limit": limit}, timeout=10)
    r.raise_for_status()
    return [{"ts": int(x["timestamp"]), "oi": float(x["openInterest"])}
            for x in r.json()["result"]["list"]]
