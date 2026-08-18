"""Regime classification and strategy eligibility gates.

The classifier is deliberately transparent and uses only completed-candle inputs.
It is a filter, not a predictive guarantee, and it never creates orders.
"""
from __future__ import annotations

import math
from typing import Any, Mapping


def _f(value: Any, default: float = math.nan) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return default
    return result if math.isfinite(result) else default


def classify_regime(row: Mapping[str, Any]) -> dict[str, Any]:
    adx = _f(row.get("adx"))
    ema20 = _f(row.get("ema20"))
    ema50 = _f(row.get("ema50"))
    rv_pct = _f(row.get("rv_pct"))
    dvol_pct = _f(row.get("dvol_pct"), 0.5)
    if not all(math.isfinite(value) for value in (adx, ema20, ema50, rv_pct, dvol_pct)):
        return {
            "regime": "UNKNOWN",
            "risk_state": "BLOCKED",
            "trend_state": "UNKNOWN",
            "volatility_state": "UNKNOWN",
            "reasons": ["missing_or_nonfinite_regime_inputs"],
        }

    if rv_pct > 0.95 or dvol_pct > 0.95:
        volatility_state = "EXTREME"
    elif rv_pct > 0.80 or dvol_pct > 0.80:
        volatility_state = "HIGH"
    elif rv_pct < 0.20 and dvol_pct < 0.20:
        volatility_state = "LOW"
    else:
        volatility_state = "NORMAL"

    if adx >= 25.0 and ema20 > ema50:
        trend_state = "UP"
        base_regime = "TREND_UP"
    elif adx >= 25.0 and ema20 < ema50:
        trend_state = "DOWN"
        base_regime = "TREND_DOWN"
    elif adx < 20.0:
        trend_state = "FLAT"
        base_regime = "RANGE"
    else:
        trend_state = "TRANSITION"
        base_regime = "TRANSITION"

    risk_state = "BLOCKED" if volatility_state == "EXTREME" else "OPEN"
    regime = "RISK_OFF" if risk_state == "BLOCKED" else base_regime
    return {
        "regime": regime,
        "risk_state": risk_state,
        "trend_state": trend_state,
        "volatility_state": volatility_state,
        "adx": adx,
        "rv_pct": rv_pct,
        "dvol_pct": dvol_pct,
        "reasons": [],
    }


def strategy_allowed(strategy_id: str, candidate: Mapping[str, Any], regime: Mapping[str, Any]) -> tuple[bool, str]:
    """Return whether a candidate survives the regime filter."""
    if regime.get("risk_state") != "OPEN":
        return False, "risk_off_or_unknown"
    strategy = str(strategy_id)
    regime_name = str(regime.get("regime"))
    if strategy == "trend_following":
        if regime_name not in {"TREND_UP", "TREND_DOWN"}:
            return False, "trend_strategy_requires_directional_regime"
        expected = "BUY" if regime_name == "TREND_UP" else "SELL"
        if candidate.get("side") != expected:
            return False, "trend_side_disagrees_with_regime"
    elif strategy == "mean_reversion":
        if regime_name != "RANGE":
            return False, "mean_reversion_requires_range_regime"
    elif strategy == "funding_divergence":
        if regime_name == "RISK_OFF":
            return False, "funding_candidate_blocked_in_extreme_volatility"
    return True, "allowed"


def filter_candidates(candidates: list[Mapping[str, Any]], row: Mapping[str, Any]) -> dict[str, Any]:
    regime = classify_regime(row)
    accepted = []
    rejected = []
    for candidate in candidates:
        allowed, reason = strategy_allowed(candidate.get("strategy_id", "unknown"), candidate, regime)
        record = {**dict(candidate), "regime": regime.get("regime"), "regime_reason": reason}
        (accepted if allowed else rejected).append(record)
    return {
        "mode": "PAPER_ONLY",
        "regime": regime,
        "accepted": accepted,
        "rejected": rejected,
        "risk_state": regime.get("risk_state"),
        "action": "REVIEW_PAPER_CANDIDATES" if accepted else "HOLD",
    }
