# ============================================================
# purged_validation.py — Combinatorial Purged CV (Track 1)
# N=6 folds, K=2 test → C(6,2)=15 OOS paths
# python purged_validation.py --days 60 [--with-foi]
# ============================================================
import argparse, itertools, os
import numpy as np
from backtest_v2 import run, metrics

EMBARGO_BARS = 48  # 720min / 15min = max trade horizon

def make_folds(n_bars, n_splits=6, n_test=2):
    edges = np.linspace(0, n_bars, n_splits + 1).astype(int)
    folds = [(edges[k], edges[k + 1]) for k in range(n_splits)]
    for test_idxs in itertools.combinations(range(n_splits), n_test):
        test = [folds[k] for k in test_idxs]
        yield test

def overlaps(o, c, test):
    return any(o <= te and c >= ts for ts, te in test)


def trade_interval(trade):
    """Return a trade's label interval in bar units, preserving missing close labels."""
    open_bar = int(trade["open_bar"])
    return open_bar, int(trade.get("close_bar", open_bar))


def embargoed_ranges(test, n_bars, embargo):
    """Extend each test fold forward to prevent post-test information leakage."""
    return [(start, min(n_bars - 1, end + embargo)) for start, end in test]


def purged_train_trades(trades, test, n_bars, embargo=EMBARGO_BARS):
    """Exclude training labels overlapping a test fold or its forward embargo window."""
    protected = embargoed_ranges(test, n_bars, embargo)
    return [trade for trade in trades if not overlaps(*trade_interval(trade), protected)]


def oos_trades(trades, test):
    """Select labels whose decision time belongs to one of the held-out folds."""
    return [trade for trade in trades
            if any(start <= int(trade["open_bar"]) <= end for start, end in test)]


def path_metrics(oos):
    if not oos:
        return None
    pnls = np.array([t["pnl_pct"] for t in oos])
    eq = np.prod(1 + pnls / 100)
    wins = pnls[pnls > 0]
    return {"n": len(pnls),
            "net_pct": round((eq - 1) * 100, 2),
            "win_rate": round(100 * len(wins) / len(pnls), 1),
            "expectancy": round(float(pnls.mean()), 3)}


def run_purged_cpcv(trades, n_bars, n_splits=6, n_test=2, embargo=EMBARGO_BARS):
    """Build OOS paths and record the training pool remaining after purging and embargo."""
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

def dist(vals):
    a = np.array(vals)
    return (round(float(np.percentile(a, 5)), 2),
            round(float(np.percentile(a, 50)), 2),
            round(float(np.percentile(a, 95)), 2))

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=60)
    ap.add_argument("--with-foi", action="store_true")
    a = ap.parse_args()

    res = run(cfg_symbol(), a.days, a.with_foi)
    trades = res["trades"]
    n_bars = res["n_bars"]
    if len(trades) < 20:
        print(f"[purged] only {len(trades)} trades — insufficient")
        return

    paths = run_purged_cpcv(trades, n_bars)

    nets = [p["net_pct"] for p in paths]
    exps = [p["expectancy"] for p in paths]
    wrs = [p["win_rate"] for p in paths]

    # static 70/30 comparison
    split = int(n_bars * 0.7)
    static_oos = [t for t in trades if t["open_bar"] >= split]
    static_net = (np.prod([1 + t["pnl_pct"] / 100 for t in static_oos]) - 1) * 100 \
        if static_oos else 0.0
    pctile = 100 * sum(1 for n in nets if n <= static_net) / max(len(nets), 1)

    md = f"""# Purged CPCV Validation — {a.days} days
Trades: {len(trades)} | N=6 folds, K=2 → {len(paths)} OOS paths
Purge: overlapping-outcome train trades | Embargo: {EMBARGO_BARS} bars
Mean retained training labels: {np.mean([p['train_n'] for p in paths]):.1f} | Mean purged labels: {np.mean([p['purged_n'] for p in paths]):.1f}

## OOS Path Distribution
- Net %: P05 {dist(nets)[0]} | P50 {dist(nets)[1]} | P95 {dist(nets)[2]}
- Expectancy: P05 {dist(exps)[0]} | P50 {dist(exps)[1]} | P95 {dist(exps)[2]}
- Win rate: P05 {dist(wrs)[0]} | P50 {dist(wrs)[1]} | P95 {dist(wrs)[2]}

## Static 70/30 split vs CPCV
- Static OOS net: {static_net:+.2f}% → {pctile:.0f}th percentile of CPCV
- {'⚠️ static looks optimistic — trust CPCV P50' if pctile > 75 else '✅ static consistent with CPCV'}
"""
    os.makedirs("reports", exist_ok=True)
    with open("reports/purged_validation.md", "w") as f:
        f.write(md)
    print(md)

def cfg_symbol():
    import config_v2 as cfg
    return cfg.SYMBOL

if __name__ == "__main__":
    main()
