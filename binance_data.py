import requests

# NOTE: fapi.binance.com returns 451 from US IPs (GitHub runners).
# data-api.binance.vision = official public spot data, NOT geo-blocked.
BASE = "https://data-api.binance.vision"

def klines(symbol="BTCUSDT", interval="15m", limit=500):
    r = requests.get(f"{BASE}/api/v3/klines",
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

def funding_history(symbol="BTCUSDT", limit=200):
    # Kept for backtest compatibility; will fail from US (caught by try/except)
    r = requests.get("https://fapi.binance.com/fapi/v1/fundingRate",
                     params={"symbol": symbol, "limit": limit}, timeout=10)
    r.raise_for_status()
    return [{"ts": int(x["fundingTime"]), "rate": float(x["fundingRate"])}
            for x in r.json()]
