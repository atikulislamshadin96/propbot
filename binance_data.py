import requests

BASE = "https://fapi.binance.com"

def klines(symbol="BTCUSDT", interval="15m", limit=300):
    r = requests.get(f"{BASE}/fapi/v1/klines",
                     params={"symbol": symbol, "interval": interval, "limit": limit},
                     timeout=15)
    r.raise_for_status()
    rows = []
    for k in r.json():
        rows.append({
            "ts": int(k[0]), "open": float(k[1]), "high": float(k[2]),
            "low": float(k[3]), "close": float(k[4]), "volume": float(k[5]),
            "taker_buy": float(k[9]),
        })
    return rows

def funding_current(symbol="BTCUSDT"):
    r = requests.get(f"{BASE}/fapi/v1/premiumIndex",
                     params={"symbol": symbol}, timeout=10)
    r.raise_for_status()
    return float(r.json()["lastFundingRate"])

def funding_history(symbol="BTCUSDT", limit=200):
    """Historical funding rates (for divergence z-score)"""
    r = requests.get(f"{BASE}/fapi/v1/fundingRate",
                     params={"symbol": symbol, "limit": limit}, timeout=10)
    r.raise_for_status()
    return [{"ts": int(x["fundingTime"]), "rate": float(x["fundingRate"])}
            for x in r.json()]

def open_interest(symbol="BTCUSDT"):
    r = requests.get(f"{BASE}/fapi/v1/openInterest",
                     params={"symbol": symbol}, timeout=10)
    r.raise_for_status()
    return float(r.json()["openInterest"])
