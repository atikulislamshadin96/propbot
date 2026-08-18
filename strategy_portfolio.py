"""Independent paper-only strategy components and portfolio aggregation.

The registry deliberately returns candidate metadata rather than exchange orders.
Each strategy can be evaluated and validated separately before portfolio promotion.
"""
from __future__ import annotations

import math
from typing import Any, Mapping

import config_v2 as cfg
from signals_v3 import signal_from_panel_row
from regime_filter import filter_candidates


def _f(value: Any, default: float = math.nan) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return default
    return result if math.isfinite(result) else default


def _base_candidate(row: Mapping[str, Any], strategy_id: str, side: str, tags: dict[str, Any]) -> dict[str, Any] | None:
    close = _f(row.get("close"), 0.0)
    atr_value = _f(row.get("atr"), 0.0)
    if close <= 0 or atr_value <= 0:
        return None
    return {
        "mode": "PAPER_ONLY",
        "strategy_id": strategy_id,
        "timestamp": str(row.get("timestamp") or row.get("time") or ""),
        "symbol": str(row.get("symbol") or ""),
        "side": side,
        "entry": close,
        "atr": atr_value,
        "tags": tags,
        "risk_note": "Candidate only; no order instruction, leverage, margin, or liquidation action is implied.",
    }


def trend_following_candidate(row: Mapping[str, Any]) -> dict[str, Any] | None:
    """Trend continuation candidate using EMA alignment, ADX, RSI, and volume."""
    ema20 = _f(row.get("ema20"))
    ema50 = _f(row.get("ema50"))
    adx_value = _f(row.get("adx"))
    rsi_value = _f(row.get("rsi"))
    vol_ratio = _f(row.get("vol_ratio"))
    close = _f(row.get("close"))
    if not all(math.isfinite(value) for value in (ema20, ema50, adx_value, rsi_value, vol_ratio, close)):
        return None
    if adx_value < 25.0 or vol_ratio < cfg.VOL_CONFIRM_RATIO:
        return None
    if ema20 > ema50 and close > ema20 and rsi_value >= 55.0:
        return _base_candidate(
            row,
            "trend_following",
            "BUY",
            {"regime": "TREND_UP", "adx": adx_value, "rsi": rsi_value},
        )
    if ema20 < ema50 and close < ema20 and rsi_value <= 45.0:
        return _base_candidate(
            row,
            "trend_following",
            "SELL",
            {"regime": "TREND_DOWN", "adx": adx_value, "rsi": rsi_value},
        )
    return None


def mean_reversion_candidate(row: Mapping[str, Any]) -> dict[str, Any] | None:
    """Range-bound Bollinger/RSI reversal candidate with a trend-strength veto."""
    adx_value = _f(row.get("adx"))
    rsi_value = _f(row.get("rsi"))
    bb_z = _f(row.get("bb_z"))
    vol_ratio = _f(row.get("vol_ratio"))
    if not all(math.isfinite(value) for value in (adx_value, rsi_value, bb_z, vol_ratio)):
        return None
    if adx_value > 25.0 or vol_ratio <= 0.0 or vol_ratio > 1.5:
        return None
    if bb_z <= -2.0 and rsi_value <= 35.0:
        return _base_candidate(
            row,
            "mean_reversion",
            "BUY",
            {"regime": "RANGE", "bb_z": bb_z, "rsi": rsi_value},
        )
    if bb_z >= 2.0 and rsi_value >= 65.0:
        return _base_candidate(
            row,
            "mean_reversion",
            "SELL",
            {"regime": "RANGE", "bb_z": bb_z, "rsi": rsi_value},
        )
    return None


def funding_divergence_candidate(panel_row: Mapping[str, Any], coin: str = cfg.FUNDING_ACTIVE_COIN) -> dict[str, Any] | None:
    """Strict funding-divergence candidate; relaxed mode must be requested explicitly."""
    candidate = signal_from_panel_row(panel_row, coin=coin, profile="strict")
    if candidate is not None:
        candidate["strategy_id"] = "funding_divergence"
    return candidate


def evaluate_portfolio(
    candle_row: Mapping[str, Any] | None = None,
    funding_row: Mapping[str, Any] | None = None,
    *,
    coin: str = cfg.FUNDING_ACTIVE_COIN,
) -> dict[str, Any]:
    """Evaluate all independent components and return an auditable portfolio snapshot."""
    candidates: list[dict[str, Any]] = []
    if candle_row is not None:
        for builder in (trend_following_candidate, mean_reversion_candidate):
            candidate = builder(candle_row)
            if candidate is not None:
                candidates.append(candidate)
    if funding_row is not None:
        candidate = funding_divergence_candidate(funding_row, coin=coin)
        if candidate is not None:
            candidates.append(candidate)

    regime_result = filter_candidates(candidates, candle_row) if candle_row is not None else {
        "regime": {"regime": "UNKNOWN", "risk_state": "BLOCKED"},
        "accepted": [],
        "rejected": candidates,
        "risk_state": "BLOCKED",
        "action": "HOLD",
    }
    accepted = regime_result["accepted"]
    directions = {candidate["side"] for candidate in accepted if candidate.get("side") in {"BUY", "SELL"}}
    conflicts = len(directions) > 1
    return {
        "mode": "PAPER_ONLY",
        "coin": coin,
        "strategies_evaluated": ["trend_following", "mean_reversion", "funding_divergence"],
        "candidates": accepted,
        "rejected_candidates": regime_result["rejected"],
        "candidate_count": len(accepted),
        "raw_candidate_count": len(candidates),
        "regime": regime_result["regime"],
        "risk_state": regime_result["risk_state"],
        "direction_conflict": conflicts,
        "portfolio_action": "HOLD" if conflicts or not accepted else "REVIEW_PAPER_CANDIDATES",
        "risk_note": "Portfolio aggregation is diagnostic only; sizing, netting, execution, and live orders are intentionally absent.",
    }
