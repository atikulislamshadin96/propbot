"""Public funding-rate adapters for research and paper-trading validation only."""
from datetime import datetime, timedelta, timezone

import pandas as pd
import requests

from hl_funding import fetch_hl_funding_history


DYDX_INDEXER_BASE = "https://indexer.dydx.trade/v4"
DYDX_TIMEOUT = 20


def dydx_ticker(coin: str) -> str:
    """Translate a base asset into its dYdX USD perpetual ticker."""
    if not coin or not coin.isalpha():
        raise ValueError("coin must be an alphabetic base asset symbol")
    return f"{coin.upper()}-USD"


def _utc(value):
    timestamp = pd.Timestamp(value)
    return timestamp.tz_localize("UTC") if timestamp.tzinfo is None else timestamp.tz_convert("UTC")


def fetch_dydx_funding_history(coin: str, days: int = 14, page_size: int = 1000) -> pd.Series:
    """Fetch dYdX hourly funding rates through the official public Indexer route."""
    if days < 1 or page_size < 1:
        raise ValueError("days and page_size must be positive")

    start = datetime.now(timezone.utc) - timedelta(days=days)
    cursor = None
    rows = []
    for _ in range(100):
        params = {"limit": page_size}
        if cursor is not None:
            params["effectiveBeforeOrAt"] = cursor.isoformat().replace("+00:00", "Z")
        response = requests.get(
            f"{DYDX_INDEXER_BASE}/historicalFunding/{dydx_ticker(coin)}",
            params=params,
            timeout=DYDX_TIMEOUT,
        )
        response.raise_for_status()
        payload = response.json()
        batch = payload.get("historicalFunding")
        if not isinstance(batch, list) or not batch:
            break
        rows.extend(batch)
        times = [_utc(row["effectiveAt"]) for row in batch if row.get("effectiveAt")]
        if not times:
            raise ValueError("dYdX historicalFunding response did not contain effectiveAt timestamps")
        earliest = min(times)
        if earliest.to_pydatetime() <= start or len(batch) < page_size:
            break
        cursor = (earliest - pd.Timedelta(microseconds=1)).to_pydatetime()

    if not rows:
        return pd.Series(dtype=float, name="dydx_funding")
    frame = pd.DataFrame(rows)
    if not {"effectiveAt", "rate"}.issubset(frame.columns):
        raise ValueError("dYdX historicalFunding response is missing rate or effectiveAt")
    frame["time"] = pd.to_datetime(frame["effectiveAt"], utc=True, errors="coerce")
    frame["rate"] = pd.to_numeric(frame["rate"], errors="coerce")
    frame = frame.dropna(subset=["time", "rate"]).drop_duplicates("time").sort_values("time")
    frame = frame[frame["time"] >= pd.Timestamp(start)]
    return frame.set_index("time")["rate"].resample("1h").last().dropna().rename("dydx_funding")


def normalized_funding_series(coin: str, days: int = 14) -> pd.DataFrame:
    """Create an hourly, no-forward-fill cross-venue funding panel with a common overlap only."""
    hl = fetch_hl_funding_history(coin, days=days).resample("1h").last().dropna().rename("hl_funding")
    dydx = fetch_dydx_funding_history(coin, days=days).resample("1h").last().dropna().rename("dydx_funding")
    panel = pd.concat([hl, dydx], axis=1, join="inner").dropna().sort_index()
    if panel.empty:
        return panel
    panel.index = pd.to_datetime(panel.index, utc=True)
    return panel[~panel.index.duplicated(keep="last")]
