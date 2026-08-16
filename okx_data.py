import requests

BASE = "https://www.okx.com"

def okx_funding_current(instId="BTC-USDT-SWAP"):
    r = requests.get(f"{BASE}/api/v5/public/funding-rate",
                     params={"instId": instId}, timeout=10)
    r.raise_for_status()
    return float(r.json()["data"][0]["fundingRate"])

def okx_funding_history(instId="BTC-USDT-SWAP", limit=96):
    r = requests.get(f"{BASE}/api/v5/public/funding-rate-history",
                     params={"instId": instId, "limit": str(limit)}, timeout=10)
    r.raise_for_status()
    return [{"ts": int(x["fundingTime"]), "rate": float(x["fundingRate"])}
            for x in r.json()["data"]]
