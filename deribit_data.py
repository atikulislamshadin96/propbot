import requests

BASE = "https://www.deribit.com/api/v2"

def get_book_summary(currency="BTC"):
    """পুরো option universe — OI + mark_iv (Track 3)"""
    r = requests.get(f"{BASE}/public/get_book_summary_by_currency",
                     params={"currency": currency, "kind": "option"}, timeout=20)
    r.raise_for_status()
    return r.json().get("result") or []

def get_ticker(instrument="BTC-PERPETUAL"):
    r = requests.get(f"{BASE}/public/ticker",
                     params={"instrument_name": instrument}, timeout=10)
    r.raise_for_status()
    return r.json().get("result") or {}
