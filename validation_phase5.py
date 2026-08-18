"""Phase 5 validation for the independent strategy components.

All metrics are historical research estimates. The validator does not fit a
model or authorize execution; it only partitions completed trade labels.
"""
from __future__ import annotations

import argparse
import itertools
import json
from pathlib import Path

import numpy as np

import config_v2 as cfg
from portfolio_backtest import run_strategy
from purged_validation import make_folds, embargoed_ranges, overlaps
from strategy_portfolio import mean_reversion_candidate, trend_following_candidate

REPORT_PATH = Path("reports/validation_phase5_latest.json")
MIN_LABELS = 20


def _adjusted_pnls(trades: list[dict], extra_cost_bps: float = 0.0) -> np.ndarray:
    # 1 bps = 0.01 percentage points.
    return np.asarray([float(t.get("pnl_pct") or 0.0) - extra_cost_bps / 100.0 for t in trades], dtype=float)


def metrics(trades: list[dict], extra_cost_bps: float = 0.0) -> dict:
    pnls = _adjusted_pnls(trades, extra_cost_bps)
    if len(pnls) == 0:
        return {"n": 0, "net_pct": None, "win_rate_pct": None, "profit_factor": None, "expectancy_pct": None, "max_dd_pct": None}
    wins = pnls[pnls > 0]
    losses = pnls[pnls <= 0]
    equity = np.cumprod(1 + pnls / 100.0)
    peaks = np.maximum.accumulate(np.r_[1.0, equity])[1:]
    drawdowns = (equity - peaks) / peaks * 100.0
    gross_loss = abs(float(losses.sum()))
    return {
        "n": int(len(pnls)),
        "net_pct": round(float((equity[-1] - 1.0) * 100.0), 5),
        "win_rate_pct": round(float((pnls > 0).mean() * 100.0), 3),
        "profit_factor": round(float(wins.sum() / gross_loss), 5) if gross_loss else None,
        "expectancy_pct": round(float(pnls.mean()), 6),
        "max_dd_pct": round(float(drawdowns.min()), 5),
    }


def protected_train_count(trades: list[dict], test: list[tuple[int, int]], n_bars: int, embargo: int) -> int:
    protected = embargoed_ranges(test, n_bars, embargo)
    return sum(1 for trade in trades if not overlaps(int(trade["open_bar"]), int(trade.get("close_bar", trade["open_bar"])), protected))


def oos_trades(trades: list[dict], test: list[tuple[int, int]]) -> list[dict]:
    return [
        trade for trade in trades
        if any(start <= int(trade["open_bar"]) <= end and int(trade.get("close_bar", trade["open_bar"])) <= end for start, end in test)
    ]


def walk_forward(trades: list[dict], n_bars: int, n_windows: int = 5) -> dict:
    if len(trades) < MIN_LABELS:
        return {"status": "INSUFFICIENT_LABELS", "labels": len(trades), "windows": []}
    start = int(n_bars * 0.40)
    test_size = max(int(n_bars * 0.10), 1)
    windows = []
    for index in range(n_windows):
        test_start = start + index * test_size
        test_end = min(n_bars - 1, test_start + test_size - 1)
        if test_start >= n_bars:
            break
        oos = oos_trades(trades, [(test_start, test_end)])
        windows.append({
            "window": index + 1,
            "test_start_bar": test_start,
            "test_end_bar": test_end,
            "metrics": metrics(oos),
        })
    valid = [item["metrics"] for item in windows if item["metrics"]["n"] > 0]
    return {
        "status": "OK" if valid else "NO_OOS_LABELS",
        "labels": len(trades),
        "windows": windows,
        "positive_windows": sum(1 for item in valid if item["net_pct"] > 0),
        "median_oos_profit_factor": round(float(np.median([item["profit_factor"] for item in valid if item["profit_factor"] is not None])), 5) if any(item["profit_factor"] is not None for item in valid) else None,
    }


def cpcv(trades: list[dict], n_bars: int, n_splits: int = 6, n_test: int = 2, embargo: int = 48) -> dict:
    if len(trades) < MIN_LABELS:
        return {"status": "INSUFFICIENT_LABELS", "labels": len(trades), "paths": []}
    paths = []
    for test in make_folds(n_bars, n_splits, n_test):
        oos = oos_trades(trades, test)
        if not oos:
            continue
        item = metrics(oos)
        item.update({
            "test_folds": [[int(start), int(end)] for start, end in test],
            "train_n_after_purge": protected_train_count(trades, test, n_bars, embargo),
            "purge_embargo_bars": embargo,
        })
        paths.append(item)
    nets = [path["net_pct"] for path in paths]
    return {
        "status": "OK" if paths else "NO_OOS_LABELS",
        "labels": len(trades),
        "paths": paths,
        "net_percentiles": {str(p): round(float(np.percentile(nets, p)), 5) for p in (5, 50, 95)} if nets else None,
    }


def stress(trades: list[dict], costs_bps: tuple[float, ...] = (0.0, 5.0, 10.0, 20.0)) -> list[dict]:
    return [{"extra_cost_bps": cost, "metrics": metrics(trades, cost)} for cost in costs_bps]


def run(symbols: list[str], days: int, regime_aware: bool) -> dict:
    builders = {"trend_following": trend_following_candidate, "mean_reversion": mean_reversion_candidate}
    strategies = {}
    for strategy_name, builder in builders.items():
        per_symbol = [run_strategy(symbol, days, strategy_name, builder, regime_aware=regime_aware) for symbol in symbols]
        trades = [trade for result in per_symbol for trade in result["trades"]]
        n_bars = min((result["bars"] for result in per_symbol if result["bars"]), default=0)
        strategies[strategy_name] = {
            "overall": metrics(trades),
            "walk_forward": walk_forward(trades, n_bars),
            "cpcv": cpcv(trades, n_bars),
            "stress": stress(trades),
            "per_symbol": [{"symbol": result["symbol"], "metrics": metrics(result["trades"])} for result in per_symbol],
        }
    output = {
        "mode": "RESEARCH_ONLY_PHASE5_VALIDATION",
        "days": days,
        "symbols": symbols,
        "regime_aware": regime_aware,
        "strategies": strategies,
        "limitations": [
            "No parameter fitting or model selection is performed inside held-out windows.",
            "Outcome intervals must end inside the held-out window; purging and 48-bar embargo are applied to training counts.",
            "Stress costs are additive diagnostics, not a substitute for venue-specific fill and slippage records.",
            "Results do not establish future profitability or prop-firm challenge-passing ability.",
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
    parser.add_argument("--regime-aware", action="store_true")
    args = parser.parse_args()
    run(args.symbols, args.days, args.regime_aware)
