"""Free public historical data for the advanced flow-shock strategy."""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional
import time
import requests

BASE = "https://data-api.binance.vision"
TIMEOUT = 20


def fetch_historical_klines(symbol: str, interval: str = "15m", days: int = 120, end_ts: Optional[int] = None) -> List[Dict[str, float]]:
    """Fetch spot candles in ascending order with no future data relative to end_ts."""
    if days <= 0:
        return []
    end_ms = int(end_ts if end_ts is not None else datetime.now(timezone.utc).timestamp() * 1000)
    start_ms = end_ms - days * 86400 * 1000
    rows: List[Dict[str, float]] = []
    cursor = start_ms
    interval_ms = {"1m": 60_000, "5m": 300_000, "15m": 900_000, "1h": 3_600_000}.get(interval)
    if interval_ms is None:
        raise ValueError(f"unsupported interval: {interval}")
    while cursor < end_ms:
        params = {"symbol": symbol, "interval": interval, "startTime": cursor,
                  "endTime": end_ms, "limit": 1000}
        last_error = None
        for attempt in range(3):
            try:
                r = requests.get(f"{BASE}/api/v3/klines", params=params,
                                 timeout=(8, 60))
                r.raise_for_status()
                payload = r.json()
                break
            except requests.RequestException as exc:
                last_error = exc
                if attempt == 2:
                    raise RuntimeError(f"public candle fetch failed for {symbol} at {cursor}: {exc}") from exc
                time.sleep(1.5 * (attempt + 1))
        if not payload:
            break
        for k in payload:
            ts = int(k[0])
            if ts >= end_ms:
                continue
            rows.append({"ts": ts, "open": float(k[1]), "high": float(k[2]),
                         "low": float(k[3]), "close": float(k[4]),
                         "volume": float(k[5]), "taker_buy": float(k[9])})
        last_ts = int(payload[-1][0])
        next_cursor = last_ts + interval_ms
        if next_cursor <= cursor:
            break
        cursor = next_cursor
        if len(payload) < 1000:
            break
        time.sleep(0.08)
    dedup = {int(r["ts"]): r for r in rows}
    return [dedup[k] for k in sorted(dedup)]


def fetch_symbol_panel(symbols, interval="15m", days=120, end_ts=None):
    return {symbol: fetch_historical_klines(symbol, interval, days, end_ts) for symbol in symbols}


if __name__ == "__main__":
    for symbol, rows in fetch_symbol_panel(("BTCUSDT", "ETHUSDT", "SOLUSDT"), days=3).items():
        print(symbol, len(rows), rows[0]["ts"] if rows else None, rows[-1]["ts"] if rows else None)
