"""Purged validation for legacy trades or funding-divergence event labels."""
from __future__ import annotations

import argparse
import itertools
import os

import numpy as np

from backtest_v2 import run as legacy_run

EMBARGO_BARS = 48


def make_folds(n_bars, n_splits=6, n_test=2):
    """Yield combinations of contiguous test folds."""
    edges = np.linspace(0, n_bars, n_splits + 1).astype(int)
    folds = [(edges[k], edges[k + 1]) for k in range(n_splits)]
    for test_idxs in itertools.combinations(range(n_splits), n_test):
        yield [folds[k] for k in test_idxs]


def overlaps(o, c, test):
    """Return whether an inclusive label interval intersects a protected range."""
    return any(o <= test_end and c >= test_start for test_start, test_end in test)


def trade_interval(trade):
    """Return a label interval in bar units, preserving missing close labels."""
    open_bar = int(trade["open_bar"])
    return open_bar, int(trade.get("close_bar", open_bar))


def embargoed_ranges(test, n_bars, embargo):
    """Extend each held-out fold forward to protect post-test observations."""
    return [(start, min(n_bars - 1, end + embargo)) for start, end in test]


def purged_train_trades(trades, test, n_bars, embargo=EMBARGO_BARS):
    """Exclude training labels overlapping a test fold or its embargo window."""
    protected = embargoed_ranges(test, n_bars, embargo)
    return [trade for trade in trades if not overlaps(*trade_interval(trade), protected)]


def oos_trades(trades, test):
    """Select labels whose decision time belongs to a held-out test fold."""
    return [trade for trade in trades if any(start <= int(trade["open_bar"]) <= end for start, end in test)]


def path_metrics(oos):
    """Return path-level proxy metrics or ``None`` for an empty path."""
    if not oos:
        return None
    key = "proxy_pnl_bps" if "proxy_pnl_bps" in oos[0] else "pnl_pct"
    pnls = np.array([float(trade[key]) for trade in oos])
    wins = pnls[pnls > 0]
    if key == "proxy_pnl_bps":
        net = (np.prod(1 + pnls / 10_000) - 1) * 10_000
    else:
        net = (np.prod(1 + pnls / 100) - 1) * 100
    return {
        "n": len(pnls),
        "net": round(float(net), 4),
        "win_rate": round(100 * len(wins) / len(pnls), 1),
        "expectancy": round(float(pnls.mean()), 4),
        "pnl_key": key,
    }


def run_purged_cpcv(trades, n_bars, n_splits=6, n_test=2, embargo=EMBARGO_BARS):
    """Build OOS paths after explicit overlap and embargo removal."""
    paths = []
    for test in make_folds(n_bars, n_splits, n_test):
        train = purged_train_trades(trades, test, n_bars, embargo)
        oos = oos_trades(trades, test)
        metric = path_metrics(oos)
        if metric:
            metric["train_n"] = len(train)
            metric["purged_n"] = len(trades) - len(train) - len(oos)
            paths.append(metric)
    return paths


def dist(values):
    array = np.array(values)
    return tuple(round(float(np.percentile(array, percentile)), 4) for percentile in (5, 50, 95))


def _write_report(text):
    os.makedirs("reports", exist_ok=True)
    with open("reports/purged_validation.md", "w", encoding="utf-8") as handle:
        handle.write(text)


def main():
    import config_v2 as cfg

    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=365)
    parser.add_argument("--with-foi", action="store_true", help="required only for --strategy legacy")
    parser.add_argument("--strategy", choices=("divergence", "legacy"), default="divergence")
    parser.add_argument("--coin", default=cfg.FUNDING_ACTIVE_COIN)
    args = parser.parse_args()

    if args.strategy == "divergence":
        from divergence_backtest import run as divergence_run

        result = divergence_run(args.coin, args.days)
        trades = result["events"]
        n_bars = len(result["panel"])
        label = "funding-proxy bps"
    else:
        result = legacy_run(cfg.SYMBOL, args.days, args.with_foi)
        trades = result["trades"]
        n_bars = result["n_bars"]
        label = "price pnl %"

    if len(trades) < 20:
        report = (
            f"# Purged CPCV Validation — {args.days} days\n\n"
            f"Strategy: `{args.strategy}` | labels: `{len(trades)}` | bars: `{n_bars}`\n\n"
            "**Insufficient evidence:** at least 20 non-overlapping labels are required before CPCV statistics are reported."
            " No performance claim is made.\n"
        )
        _write_report(report)
        print(report)
        return

    paths = run_purged_cpcv(trades, n_bars)
    nets = [path["net"] for path in paths]
    exps = [path["expectancy"] for path in paths]
    wrs = [path["win_rate"] for path in paths]
    split = int(n_bars * 0.7)
    key = "proxy_pnl_bps" if "proxy_pnl_bps" in trades[0] else "pnl_pct"
    static_oos = [trade for trade in trades if int(trade["open_bar"]) >= split]
    scale = 10_000 if key == "proxy_pnl_bps" else 100
    divisor = 10_000 if key == "proxy_pnl_bps" else 100
    static_net = (np.prod([1 + float(trade[key]) / divisor for trade in static_oos]) - 1) * scale if static_oos else 0.0
    percentile = 100 * sum(1 for net in nets if net <= static_net) / max(len(nets), 1)

    report = f"""# Purged CPCV Validation — {args.days} days

Strategy: `{args.strategy}` | labels: `{len(trades)}` | N=6 folds, K=2 → `{len(paths)}` OOS paths
Purge: overlapping outcome labels | Embargo: `{EMBARGO_BARS}` bars | Metric: `{label}`
Mean retained training labels: `{np.mean([path['train_n'] for path in paths]):.1f}` | Mean purged labels: `{np.mean([path['purged_n'] for path in paths]):.1f}`

## OOS Path Distribution

- Net: P05 `{dist(nets)[0]}` | P50 `{dist(nets)[1]}` | P95 `{dist(nets)[2]}`
- Expectancy: P05 `{dist(exps)[0]}` | P50 `{dist(exps)[1]}` | P95 `{dist(exps)[2]}`
- Win rate: P05 `{dist(wrs)[0]}` | P50 `{dist(wrs)[1]}` | P95 `{dist(wrs)[2]}`

## Static 70/30 comparison

- Static OOS net: `{static_net:+.4f}` → `{percentile:.0f}th` percentile of CPCV
- {'Static looks optimistic; trust CPCV P50.' if percentile > 75 else 'Static is directionally consistent with CPCV.'}
"""
    _write_report(report)
    print(report)


if __name__ == "__main__":
    main()
