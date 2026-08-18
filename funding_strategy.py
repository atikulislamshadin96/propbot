"""Conservative cross-venue funding-divergence logic for research and paper-trading candidates."""
import pandas as pd

import config_v2 as cfg


REQUIRED_COLUMNS = {"hl_funding", "dydx_funding"}


def divergence_panel(panel: pd.DataFrame, window_hours: int = cfg.FUNDING_Z_WINDOW_HOURS) -> pd.DataFrame:
    """Calculate an hourly spread and trailing z-score without imputation or future information."""
    if not REQUIRED_COLUMNS.issubset(panel.columns):
        raise ValueError(f"panel must contain {sorted(REQUIRED_COLUMNS)}")
    output = panel.copy().dropna().sort_index()
    output["spread"] = output["hl_funding"] - output["dydx_funding"]
    rolling = output["spread"].rolling(window_hours, min_periods=cfg.FUNDING_MIN_HISTORY_HOURS)
    output["spread_z"] = (output["spread"] - rolling.mean()) / rolling.std(ddof=0).replace(0.0, pd.NA)
    return output.dropna(subset=["spread_z"])


def paper_candidate(panel: pd.DataFrame):
    """Return a paper-only, cost-gated funding candidate, or None when evidence is insufficient."""
    scored = divergence_panel(panel)
    if scored.empty:
        return None
    latest = scored.iloc[-1]
    spread = float(latest["spread"])
    spread_z = float(latest["spread_z"])
    expected_hold_bps = abs(spread) * cfg.FUNDING_EXPECTED_HOLD_HOURS * 10_000
    required_bps = cfg.FUNDING_ROUNDTRIP_COST_BPS * cfg.FUNDING_COST_BUFFER
    if abs(spread_z) < cfg.FUNDING_Z_ENTRY or expected_hold_bps < required_bps:
        return None
    if spread > 0:
        receive_leg, pay_leg = "SHORT Hyperliquid", "LONG dYdX"
    else:
        receive_leg, pay_leg = "SHORT dYdX", "LONG Hyperliquid"
    return {
        "mode": "PAPER_ONLY",
        "timestamp": scored.index[-1].isoformat(),
        "coin": cfg.FUNDING_ACTIVE_COIN,
        "receive_leg": receive_leg,
        "pay_leg": pay_leg,
        "hl_hourly_rate": float(latest["hl_funding"]),
        "dydx_hourly_rate": float(latest["dydx_funding"]),
        "spread_hourly": spread,
        "spread_z": spread_z,
        "expected_hold_bps": expected_hold_bps,
        "required_cost_bps": required_bps,
        "expected_net_bps_before_basis_risk": expected_hold_bps - required_bps,
        "risk_note": "Candidate only. Basis, fills, position-size matching, funding changes, and venue risk are not modeled.",
    }
