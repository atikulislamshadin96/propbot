"""Cross-venue funding-divergence signal logic.

This module emits research/paper candidates only. It intentionally does not
produce exchange orders, leverage, margin, liquidation, or single-leg price
stops because a funding-arbitrage candidate is a paired position.
"""
from __future__ import annotations

import math
from typing import Any, Mapping

import config_v2 as cfg


def _finite_float(value: Any, default: float = 0.0) -> float:
    """Return a finite float or ``default`` for missing/invalid values."""
    try:
        result = float(value)
    except (TypeError, ValueError):
        return default
    return result if math.isfinite(result) else default


def evaluate_divergence(
    row: Mapping[str, Any],
    extra: Mapping[str, Any],
    *,
    is_backtest: bool = False,
    profile: str = "strict",
) -> dict[str, Any] | None:
    """Evaluate a completed cross-venue funding observation.

    A positive spread means Hyperliquid pays more funding than dYdX, so the
    candidate receives on Hyperliquid by shorting there and hedges with a long
    dYdX leg. A negative spread reverses the venue legs. The rule is
    deliberately identical in research, backtest, and live-paper paths;
    ``is_backtest`` is retained only for call-site compatibility.

    The function fails closed when the z-score, funding observations, or cost
    estimate are unavailable. It returns a descriptive candidate rather than
    an order instruction.
    """
    del is_backtest  # The signal must not diverge between research and live paths.
    if profile not in {"strict", "research_relaxed"}:
        raise ValueError("profile must be strict or research_relaxed")

    hl_rate = _finite_float(extra.get("hl_funding"), default=math.nan)
    dydx_rate = _finite_float(extra.get("dydx_funding"), default=math.nan)
    spread = _finite_float(extra.get("spread"), default=math.nan)
    spread_z = _finite_float(extra.get("spread_z"), default=math.nan)
    history_hours = int(_finite_float(extra.get("history_hours"), default=0.0))

    values = (hl_rate, dydx_rate, spread, spread_z)
    if not all(math.isfinite(value) for value in values):
        return None
    if history_hours < cfg.FUNDING_MIN_HISTORY_HOURS:
        return None
    expected_hold_bps = abs(spread) * cfg.FUNDING_EXPECTED_HOLD_HOURS * 10_000
    required_cost_bps = cfg.FUNDING_ROUNDTRIP_COST_BPS * cfg.FUNDING_COST_BUFFER
    if profile == "strict":
        z_threshold = cfg.FUNDING_Z_ENTRY
        gross_threshold_bps = required_cost_bps
        mode = "PAPER_ONLY"
    else:
        z_threshold = _finite_float(
            extra.get("adaptive_z_threshold"), default=cfg.FUNDING_RESEARCH_Z_MIN
        )
        gross_threshold_bps = _finite_float(
            extra.get("adaptive_bps_threshold"), default=cfg.FUNDING_RESEARCH_BPS_MIN
        )
        mode = "RESEARCH_ONLY_RELAXED"
    if abs(spread_z) < z_threshold or expected_hold_bps < gross_threshold_bps:
        return None

    if spread > 0:
        side = "SHORT_HL_LONG_DYDX"
        receive_leg, pay_leg = "SHORT Hyperliquid", "LONG dYdX"
    elif spread < 0:
        side = "LONG_HL_SHORT_DYDX"
        receive_leg, pay_leg = "SHORT dYdX", "LONG Hyperliquid"
    else:
        return None

    timestamp = row.get("timestamp") or row.get("time")
    timestamp_text = timestamp.isoformat() if hasattr(timestamp, "isoformat") else str(timestamp or "")
    return {
        "mode": mode,
        "timestamp": timestamp_text,
        "coin": str(extra.get("coin") or cfg.FUNDING_ACTIVE_COIN).upper(),
        "side": side,
        "receive_leg": receive_leg,
        "pay_leg": pay_leg,
        "hl_hourly_rate": hl_rate,
        "dydx_hourly_rate": dydx_rate,
        "spread_hourly": spread,
        "spread_z": spread_z,
        "history_hours": history_hours,
        "expected_hold_hours": cfg.FUNDING_EXPECTED_HOLD_HOURS,
        "expected_gross_bps": expected_hold_bps,
        "required_cost_bps": required_cost_bps,
        "expected_net_bps_before_basis_risk": expected_hold_bps - required_cost_bps,
        "risk_note": (
            "Candidate only. Basis, fills, position-size matching, funding changes, "
            "borrow, margin, liquidation, settlement, capacity, and venue risk are "
            "not modeled. No order should be inferred from this record."
        ),
    }


def signal_from_panel_row(
    row: Mapping[str, Any],
    *,
    coin: str | None = None,
    profile: str = "strict",
) -> dict[str, Any] | None:
    """Build a candidate from a scored funding-panel row."""
    extra = {
        "coin": coin or cfg.FUNDING_ACTIVE_COIN,
        "hl_funding": row.get("hl_funding"),
        "dydx_funding": row.get("dydx_funding"),
        "spread": row.get("spread"),
        "spread_z": row.get("spread_z"),
        "history_hours": row.get("history_hours", cfg.FUNDING_MIN_HISTORY_HOURS),
        "adaptive_z_threshold": row.get("adaptive_z_threshold"),
        "adaptive_bps_threshold": row.get("adaptive_bps_threshold"),
    }
    return evaluate_divergence(row, extra, profile=profile)
