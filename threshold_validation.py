"""Phase 1 threshold-relaxation and signal-frequency validation.

This module measures sensitivity only. It never creates an order candidate and
keeps the existing economic cost gate visible in the output.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

import config_v2 as cfg
from funding_data import normalized_funding_series
from funding_strategy import divergence_panel

REPORT_DIR = Path("reports")
Z_GRID = (1.5, 1.75, 2.0, 2.25, 2.5)
BPS_GRID = (15.0, 20.0, 25.0, 30.0, 35.0)


def add_adaptive_thresholds(scored: pd.DataFrame) -> pd.DataFrame:
    """Add trailing volatility percentile and adaptive threshold columns."""
    output = scored.copy()
    volatility = output["spread"].rolling(
        cfg.FUNDING_Z_WINDOW_HOURS,
        min_periods=cfg.FUNDING_MIN_HISTORY_HOURS,
    ).std(ddof=0)
    # Rolling rank uses only the current and past volatility observations.
    percentile = volatility.rolling(
        cfg.FUNDING_VOL_PERCENTILE_WINDOW_HOURS,
        min_periods=cfg.FUNDING_MIN_HISTORY_HOURS,
    ).rank(pct=True).shift(1)
    output["volatility_7d"] = volatility
    output["vol_percentile"] = percentile.clip(0.0, 1.0)
    output["adaptive_z_threshold"] = (
        cfg.FUNDING_RESEARCH_Z_MIN + output["vol_percentile"]
    ).clip(cfg.FUNDING_RESEARCH_Z_MIN, cfg.FUNDING_RESEARCH_Z_MAX)
    output["adaptive_bps_threshold"] = (
        20.0 + output["vol_percentile"] * 15.0
    ).clip(cfg.FUNDING_RESEARCH_BPS_MIN, cfg.FUNDING_RESEARCH_BPS_MAX)
    output["spread_bps"] = output["spread"].abs() * 10_000.0
    output["expected_gross_bps"] = (
        output["spread"].abs() * cfg.FUNDING_EXPECTED_HOLD_HOURS * 10_000.0
    )
    output["required_cost_bps"] = cfg.FUNDING_ROUNDTRIP_COST_BPS * cfg.FUNDING_COST_BUFFER
    output["adaptive_threshold_pass"] = (
        output["spread_z"].abs() >= output["adaptive_z_threshold"]
    ) & (output["expected_gross_bps"] >= output["adaptive_bps_threshold"])
    output["economic_cost_pass"] = output["expected_gross_bps"] >= output["required_cost_bps"]
    return output.dropna(
        subset=["vol_percentile", "adaptive_z_threshold", "adaptive_bps_threshold"]
    )


def _entry_indices(mask: Iterable[bool], cooldown_hours: int = cfg.FUNDING_EXPECTED_HOLD_HOURS) -> list[int]:
    """Convert a boolean trigger series into non-overlapping entry indices."""
    entries: list[int] = []
    next_allowed = -1
    for index, triggered in enumerate(mask):
        if bool(triggered) and index >= next_allowed:
            entries.append(index)
            next_allowed = index + cooldown_hours
    return entries


def count_triggers(
    scored: pd.DataFrame,
    z_threshold: float | None = None,
    bps_threshold: float | None = None,
    *,
    adaptive: bool = False,
    economic_only: bool = False,
) -> dict:
    """Count raw and non-overlapping triggers for one threshold rule."""
    if adaptive:
        mask = scored["adaptive_threshold_pass"].fillna(False)
        label = "adaptive"
    else:
        mask = (scored["spread_z"].abs() >= float(z_threshold)) & (
            scored["expected_gross_bps"] >= float(bps_threshold)
        )
        label = f"z{float(z_threshold):g}_bps{float(bps_threshold):g}"
    if economic_only:
        mask = mask & scored["economic_cost_pass"].fillna(False)
    raw = int(mask.sum())
    entries = _entry_indices(mask.to_numpy())
    periods = max((scored.index[-1] - scored.index[0]).total_seconds() / 604_800.0, 1 / 7)
    return {
        "rule": label,
        "economic_only": economic_only,
        "raw_triggers": raw,
        "non_overlapping_entries": len(entries),
        "weeks_observed": round(periods, 3),
        "entries_per_week": round(len(entries) / periods, 4),
    }


def validate_panel(panel: pd.DataFrame, coin: str = cfg.FUNDING_ACTIVE_COIN) -> dict:
    """Produce a complete threshold grid and adaptive-threshold summary."""
    scored = add_adaptive_thresholds(divergence_panel(panel))
    rows = []
    for z_threshold in Z_GRID:
        for bps_threshold in BPS_GRID:
            result = count_triggers(scored, z_threshold, bps_threshold)
            result.update({"z_threshold": z_threshold, "bps_threshold": bps_threshold})
            rows.append(result)
    adaptive = count_triggers(scored, adaptive=True)
    adaptive_economic = count_triggers(scored, adaptive=True, economic_only=True)
    cost_sensitivity = []
    for z_threshold in (1.5, 2.0, 2.5):
        for cost_bps in (0.0, 5.0, 10.0, 15.0, 20.0, 25.0, 30.0, 37.5):
            cost_sensitivity.append(
                {
                    **count_triggers(scored, z_threshold, cost_bps),
                    "z_threshold": z_threshold,
                    "expected_gross_threshold_bps": cost_bps,
                }
            )
    quantiles = scored["expected_gross_bps"].quantile([0.5, 0.75, 0.9, 0.95, 0.99]).to_dict()
    strict = count_triggers(
        scored,
        cfg.FUNDING_Z_ENTRY,
        cfg.FUNDING_ROUNDTRIP_COST_BPS * cfg.FUNDING_COST_BUFFER,
        economic_only=True,
    )
    z_only = count_triggers(scored, cfg.FUNDING_Z_ENTRY, 0.0)
    return {
        "mode": "THRESHOLD_SENSITIVITY_RESEARCH_ONLY",
        "coin": coin,
        "panel_observations": int(len(panel)),
        "scored_observations": int(len(scored)),
        "lookback_days_requested": None,
        "strict_current_rule": strict,
        "z_only_comparator": z_only,
        "adaptive_rule": adaptive,
        "adaptive_economic_cost_gated": adaptive_economic,
        "expected_gross_bps_quantiles": {str(key): round(float(value), 4) for key, value in quantiles.items()},
        "cost_sensitivity": cost_sensitivity,
        "threshold_grid": rows,
        "parameters": {
            "z_range": [cfg.FUNDING_RESEARCH_Z_MIN, cfg.FUNDING_RESEARCH_Z_MAX],
            "bps_range": [cfg.FUNDING_RESEARCH_BPS_MIN, cfg.FUNDING_RESEARCH_BPS_MAX],
            "volatility_lookback_hours": cfg.FUNDING_Z_WINDOW_HOURS,
            "percentile_lookback_hours": cfg.FUNDING_VOL_PERCENTILE_WINDOW_HOURS,
            "cooldown_hours": cfg.FUNDING_EXPECTED_HOLD_HOURS,
            "economic_cost_gate_bps": cfg.FUNDING_ROUNDTRIP_COST_BPS * cfg.FUNDING_COST_BUFFER,
        },
        "limitations": [
            "Counts are signal-frequency diagnostics, not profitability results.",
            "Thresholds are calculated from trailing observations only; the first warm-up period is excluded.",
            "No orders, fills, basis PnL, margin, liquidation, capacity, or venue risk are modeled.",
        ],
    }


def render_markdown(result: dict) -> str:
    """Render a compact report for daily review."""
    adaptive = result["adaptive_rule"]
    gated = result["adaptive_economic_cost_gated"]
    lines = [
        "# Phase 1 — Threshold Relaxation and Signal Frequency",
        "",
        "Mode: **research-only; no orders are sent.**",
        f"Coin: `{result['coin']}` | panel: `{result['panel_observations']}` | scored: `{result['scored_observations']}`",
        "",
        "## Summary",
        "",
        "| Rule | Raw triggers | Non-overlapping entries | Entries/week |",
        "|---|---:|---:|---:|",
        f"| Current rule (z + 37.5 bps cost gate) | {result['strict_current_rule']['raw_triggers']} | {result['strict_current_rule']['non_overlapping_entries']} | {result['strict_current_rule']['entries_per_week']} |",
        f"| z-score only (diagnostic) | {result['z_only_comparator']['raw_triggers']} | {result['z_only_comparator']['non_overlapping_entries']} | {result['z_only_comparator']['entries_per_week']} |",
        f"| Adaptive threshold | {adaptive['raw_triggers']} | {adaptive['non_overlapping_entries']} | {adaptive['entries_per_week']} |",
        f"| Adaptive + economic cost gate | {gated['raw_triggers']} | {gated['non_overlapping_entries']} | {gated['entries_per_week']} |",
        "",
        "## Interpretation",
        "",
        "A relaxed threshold can increase alerts, but an alert is not evidence of positive expectancy. The economic-cost-gated line is the relevant safety check; any threshold that increases frequency only by admitting observations below estimated costs remains research-only.",
        "Expected gross funding quantiles are included in the JSON report to show how much of the zero-signal problem comes from economic magnitude rather than z-score rarity.",
        "",
        "## Threshold grid",
        "",
        "| Z threshold | Expected gross funding threshold (bps) | Entries/week | Economic gate applied |",
        "|---:|---:|---:|---|",
    ]
    for row in result["threshold_grid"]:
        lines.append(
            f"| {row['z_threshold']:.2f} | {row['bps_threshold']:.1f} | {row['entries_per_week']:.4f} | No |"
        )
    lines.extend(
        [
            "",
            "## Limitations",
            "",
            "The frequency table measures historical trigger counts only. It does not establish win rate, profit factor, drawdown, or prop-firm rule compliance. Those require forward-only outcomes and execution-aware paper records.",
        ]
    )
    return "\n".join(lines) + "\n"


def main(days: int = 365, coin: str = cfg.FUNDING_ACTIVE_COIN) -> dict:
    """Fetch public data and write the Phase 1 report."""
    panel = normalized_funding_series(coin, days=days)
    result = validate_panel(panel, coin=coin)
    result["lookback_days_requested"] = days
    REPORT_DIR.mkdir(exist_ok=True)
    (REPORT_DIR / "threshold_validation_latest.json").write_text(
        json.dumps(result, indent=2, default=str) + "\n", encoding="utf-8"
    )
    (REPORT_DIR / "threshold_validation_latest.md").write_text(
        render_markdown(result), encoding="utf-8"
    )
    print(json.dumps(result, indent=2, default=str))
    return result


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=365)
    parser.add_argument("--coin", default=cfg.FUNDING_ACTIVE_COIN)
    arguments = parser.parse_args()
    main(arguments.days, arguments.coin)
