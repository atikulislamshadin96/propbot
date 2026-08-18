"""Conservative cross-venue funding-divergence logic for research and paper candidates."""
from __future__ import annotations

import pandas as pd

import config_v2 as cfg
from signals_v3 import signal_from_panel_row


REQUIRED_COLUMNS = {"hl_funding", "dydx_funding"}


def divergence_panel(panel: pd.DataFrame, window_hours: int = cfg.FUNDING_Z_WINDOW_HOURS) -> pd.DataFrame:
    """Calculate an hourly spread and trailing z-score without future information."""
    if not REQUIRED_COLUMNS.issubset(panel.columns):
        raise ValueError(f"panel must contain {sorted(REQUIRED_COLUMNS)}")
    if window_hours < cfg.FUNDING_MIN_HISTORY_HOURS:
        raise ValueError("window_hours must be at least FUNDING_MIN_HISTORY_HOURS")

    output = panel.copy().dropna().sort_index()
    output.index = pd.to_datetime(output.index, utc=True)
    output["spread"] = output["hl_funding"] - output["dydx_funding"]
    rolling = output["spread"].rolling(window_hours, min_periods=cfg.FUNDING_MIN_HISTORY_HOURS)
    output["history_hours"] = rolling.count()
    output["spread_z"] = (output["spread"] - rolling.mean()) / rolling.std(ddof=0).replace(0.0, pd.NA)
    return output.dropna(subset=["spread_z"])


def paper_candidate(panel: pd.DataFrame):
    """Return a shared-engine paper candidate, or ``None`` when gates fail."""
    scored = divergence_panel(panel)
    if scored.empty:
        return None
    latest = scored.iloc[-1].copy()
    latest["timestamp"] = scored.index[-1]
    return signal_from_panel_row(latest, coin=cfg.FUNDING_ACTIVE_COIN)
