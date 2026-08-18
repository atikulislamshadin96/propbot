"""Frequency and overlap diagnostics for independent single-leg strategies.

This is a research diagnostic: it measures candidate cadence and overlap only.
It does not simulate fills, fees, stops, funding, leverage, or live orders.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

import config_v2 as cfg
from backtest_v2 import fetch_range
from features import compute_features
from strategy_portfolio import mean_reversion_candidate, trend_following_candidate

REPORT_PATH = Path("reports/portfolio_frequency_latest.json")


def evaluate_symbol(symbol: str, days: int) -> dict:
    frame = fetch_range(symbol, cfg.INTERVAL, days)
    if frame.empty:
        return {"symbol": symbol, "bars": 0, "strategies": {}, "overlap_bars": 0}
    frame = compute_features(frame)
    counts = {"trend_following": 0, "mean_reversion": 0}
    overlap_bars = 0
    usable_bars = 0
    # Eight-hour cooldown at 15-minute cadence prevents a persistent condition
    # from being counted as dozens of separate entries.
    cooldown_bars = max(int(cfg.FUNDING_EXPECTED_HOLD_HOURS * 60 / 15), 1)
    next_allowed = {name: -1 for name in counts}
    for index, (_, row) in enumerate(frame.iterrows()):
        row_data = row.to_dict()
        trend = trend_following_candidate(row_data)
        mean_reversion = mean_reversion_candidate(row_data)
        trend_entry = trend is not None and index >= next_allowed["trend_following"]
        mean_entry = mean_reversion is not None and index >= next_allowed["mean_reversion"]
        usable_bars += int(trend_entry or mean_entry)
        counts["trend_following"] += int(trend_entry)
        counts["mean_reversion"] += int(mean_entry)
        overlap_bars += int(trend_entry and mean_entry)
        if trend_entry:
            next_allowed["trend_following"] = index + cooldown_bars
        if mean_entry:
            next_allowed["mean_reversion"] = index + cooldown_bars
    weeks = max(days / 7.0, 1 / 7.0)
    return {
        "symbol": symbol,
        "bars": int(len(frame)),
        "usable_signal_bars": usable_bars,
        "overlap_bars": overlap_bars,
        "cooldown_bars": cooldown_bars,

        "strategies": {
            name: {"signals": value, "signals_per_week": round(value / weeks, 4)}
            for name, value in counts.items()
        },
    }


def run(symbols: list[str] | None = None, days: int = 90) -> dict:
    symbols = symbols or cfg.SYMBOLS
    results = [evaluate_symbol(symbol, days) for symbol in symbols]
    total_counts = {"trend_following": 0, "mean_reversion": 0}
    total_bars = 0
    total_overlap = 0
    for result in results:
        total_bars += result["bars"]
        total_overlap += result["overlap_bars"]
        for name in total_counts:
            total_counts[name] += result["strategies"].get(name, {}).get("signals", 0)
    weeks = max(days / 7.0, 1 / 7.0)
    output = {
        "mode": "RESEARCH_ONLY_FREQUENCY",
        "days": days,
        "symbols": symbols,
        "results": results,
        "portfolio": {
            "bars": total_bars,
            "overlap_bars": total_overlap,
            "strategy_signals": total_counts,
            "signals_per_week": {name: round(value / weeks, 4) for name, value in total_counts.items()},
        },
        "limitations": [
            "Frequency and overlap only; no PnL, fills, slippage, or risk-adjusted returns are estimated.",
            "Strategies are counted independently; portfolio netting and capital allocation are not modeled.",
            "The funding-divergence component is validated separately because it uses hourly cross-venue data.",
        ],
    }
    REPORT_PATH.parent.mkdir(exist_ok=True)
    REPORT_PATH.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(output, indent=2))
    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=90)
    parser.add_argument("--symbols", nargs="+", default=cfg.SYMBOLS)
    args = parser.parse_args()
    run(args.symbols, args.days)
