# ============================================================
# hl_funding.py — Hyperliquid funding history fetcher
# Paginated REST, ~5 calls for 90 days, ~1 second per coin
# US-accessible, no API key needed
# + Patch A: On-disk parquet cache
# ============================================================
import os
import time
import requests
import numpy as np
import pandas as pd
from datetime import datetime, timezone

BASE = "https://api.hyperliquid.xyz/info"
TIMEOUT = 15
ROWS_PER_CALL = 500
CALL_SLEEP = 0.2
CACHE_DIR = "data/hl_funding"


def _cache_path(coin, days):
    os.makedirs(CACHE_DIR, exist_ok=True)
    return os.path.join(CACHE_DIR, f"{coin}_{days}d.parquet")


def fetch_hl_funding_history(coin, days=90):
    """
    Fetch hourly funding rate history from Hyperliquid.
    Returns pandas Series indexed by UTC datetime.
    Uses on-disk parquet cache (24h TTL).
    """
    cache_file = _cache_path(coin, days)

    # Check cache (24h TTL)
    if os.path.exists(cache_file):
        mtime = os.path.getmtime(cache_file)
        age_hours = (time.time() - mtime) / 3600
        if age_hours < 24:
            try:
                df = pd.read_parquet(cache_file)
                series = pd.Series(df["fundingRate"].values,
                                   index=pd.to_datetime(df["time"], utc=True),
                                   name="hl_funding")
                print(f"[CACHE] hl_funding {coin}: {len(series)} rows (age {age_hours:.1f}h)")
                return series
            except Exception:
                pass  # Cache corrupt, re-fetch

    # Fetch from API
    try:
        now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
        start_ms = now_ms - days * 86400 * 1000
        all_rows = []
        cursor = start_ms

        while cursor < now_ms:
            try:
                r = requests.post(BASE,
                                  json={"type": "fundingHistory",
                                        "coin": coin,
                                        "startTime": cursor},
                                  timeout=TIMEOUT)
                r.raise_for_status()
                batch = r.json()
                if not batch or not isinstance(batch, list):
                    break
                all_rows.extend(batch)
                last_ts = batch[-1].get("time", cursor)
                if last_ts <= cursor:
                    break
                cursor = last_ts + 1
                time.sleep(CALL_SLEEP)
            except Exception as e:
                print(f"[WARN] hl_funding fetch error for {coin}: {e}")
                break

        if not all_rows:
            print(f"[WARN] hl_funding: no data for {coin}")
            return pd.Series(dtype=float)

        # Deduplicate by timestamp
        df = pd.DataFrame(all_rows)
        df = df.drop_duplicates(subset="time").sort_values("time")

        # Save to cache
        try:
            df.to_parquet(cache_file, index=False)
        except Exception:
            pass  # Cache write failure is non-fatal

        idx = pd.to_datetime(df["time"], unit="ms", utc=True)
        series = pd.Series(df["fundingRate"].astype(float).values,
                           index=idx, name="hl_funding")
        print(f"[INFO] hl_funding {coin}: {len(series)} rows, "
              f"{(series.index[-1] - series.index[0]).days} days")
        return series

    except Exception as e:
        print(f"[ERROR] hl_funding failed for {coin}: {e}")
        return pd.Series(dtype=float)


def compute_funding_zscore(series, window_hours=168):
    """
    Compute rolling z-score of funding rate.
    window_hours=168 = 7 days.
    """
    if len(series) < window_hours:
        return pd.Series(np.nan, index=series.index)
    mean = series.rolling(window_hours, min_periods=window_hours // 2).mean()
    std = series.rolling(window_hours, min_periods=window_hours // 2).std()
    z = (series - mean) / std.replace(0, np.nan)
    return z.fillna(0.0)


def get_hl_funding_features(coin, days=90):
    """
    Fetch funding history + compute z-score.
    Returns DataFrame with columns: time, hl_funding, hl_funding_z
    """
    series = fetch_hl_funding_history(coin, days)
    if len(series) == 0:
        return pd.DataFrame(columns=["time", "hl_funding", "hl_funding_z"])

    z = compute_funding_zscore(series)
    df = pd.DataFrame({
        "time": series.index,
        "hl_funding": series.values,
        "hl_funding_z": z.values
    })
    return df


if __name__ == "__main__":
    for coin in ["BTC", "ETH", "SOL"]:
        df = get_hl_funding_features(coin, days=90)
        if len(df) > 0:
            print(f"{coin}: {len(df)} rows, "
                  f"z range [{df['hl_funding_z'].min():.2f}, "
                  f"{df['hl_funding_z'].max():.2f}]")
        else:
            print(f"{coin}: NO DATA")
