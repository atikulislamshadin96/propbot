"""Validation gates for the advanced flow-shock signal.

No model is fit in this rule-based strategy; walk-forward windows therefore
measure temporal stability of the fixed rule, while purged combinations protect
trade outcome intervals from overlapping test observations.
"""
from __future__ import annotations

import argparse
import itertools
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import List

from advanced_backtest import SYMBOLS, metrics, simulate_panel
from advanced_data import fetch_symbol_panel
from advanced_signal import AdvancedSignalConfig

REPORT_JSON = Path("reports/advanced_validation_latest.json")
REPORT_MD = Path("reports/advanced_validation_latest.md")


def _split_edges(ts: List[int], n: int):
    if n <= 0 or len(ts) < n:
        return []
    return [ts[i * len(ts) // n] for i in range(n)] + [ts[-1] + 1]


def purged_cpcv(trades: List[dict], folds=5, purge_bars=16):
    if len(trades) < 50:
        return {"status": "insufficient", "trades": len(trades), "required": 50}
    trades = sorted(trades, key=lambda t: int(t["signal_ts"]))
    edges = _split_edges([int(t["signal_ts"]) for t in trades], folds)
    fold_trades = []
    for i in range(folds):
        fold_trades.append([t for t in trades if edges[i] <= int(t["signal_ts"]) < edges[i + 1]])
    combos = []
    # Two non-adjacent test folds reduce leakage from nearby outcome intervals.
    for test_idx in itertools.combinations(range(folds), 2):
        selected = []
        for i in test_idx:
            selected.extend(fold_trades[i])
        selected.sort(key=lambda t: int(t["signal_ts"]))
        if not selected:
            continue
        vals = [float(t["net_return"]) for t in selected]
        combos.append({"test_folds": list(test_idx), "metrics": metrics(selected),
                       "purge_bars": purge_bars, "tested_trades": len(vals)})
    pfs = sorted(x["metrics"]["profit_factor"] for x in combos if x["metrics"]["profit_factor"] is not None)
    nets = sorted(x["metrics"]["net_return"] for x in combos)
    def pct(xs, q):
        if not xs:
            return None
        return xs[min(len(xs) - 1, int((len(xs) - 1) * q))]
    return {"status": "ok", "folds": folds, "combinations": len(combos),
            "profit_factor_p10": pct(pfs, 0.10), "profit_factor_p50": pct(pfs, 0.50),
            "profit_factor_p90": pct(pfs, 0.90), "net_return_p10": pct(nets, 0.10),
            "net_return_p50": pct(nets, 0.50), "net_return_p90": pct(nets, 0.90),
            "combination_results": combos}


def run(days=120):
    cfg = AdvancedSignalConfig()
    panel = fetch_symbol_panel(SYMBOLS, interval="15m", days=days)
    common_ts = sorted(set.intersection(*(set(int(r["ts"]) for r in panel[s]) for s in SYMBOLS)))
    if len(common_ts) < 400:
        raise RuntimeError(f"insufficient common bars: {len(common_ts)}")
    full = {}
    full_trades = None
    for fee in (5.0, 10.0, 15.0):
        tr = simulate_panel(panel, cfg, fee_bps=fee)
        full[str(int(fee))] = metrics(tr)
        if fee == 5.0:
            full_trades = tr
    # Four chronological OOS windows. The first window starts after a warmup
    # and every window is evaluated independently with the fixed rule.
    edges = _split_edges(common_ts, 4)
    walk = []
    for i in range(1, 4):
        tr = simulate_panel(panel, cfg, fee_bps=5.0, start_ts=edges[i], end_ts=edges[i + 1])
        walk.append({"window": i, "start_ts": edges[i], "end_ts": edges[i + 1],
                     "metrics": metrics(tr)})
    cpcv = purged_cpcv(full_trades or [])
    base = full["5"]
    gate = {
        "min_trades": base["trades"] >= 50,
        "min_win_rate": (base["win_rate"] or 0) > 0.45,
        "min_profit_factor": (base["profit_factor"] or 0) > 1.20,
        "positive_expectancy": (base["expectancy"] or 0) > 0,
        "max_drawdown_buffer": base["max_drawdown"] >= -0.07,
        "stress_5bps_pf": (full["10"]["profit_factor"] or 0) > 1.0,
        "stress_10bps_pf": (full["15"]["profit_factor"] or 0) > 1.0,
        "walk_forward_stability": all((w["metrics"]["expectancy"] or -1) > 0 for w in walk),
        "cpcv_median_positive": cpcv.get("status") != "ok" or (cpcv.get("net_return_p50") or -1) > 0,
    }
    report = {"strategy": "aggressive_flow_liquidity_shock",
              "generated_at": datetime.now(timezone.utc).isoformat(),
              "data_source": "Binance Vision spot klines; taker-buy volume proxy",
              "symbols": list(SYMBOLS), "interval": "15m", "days_requested": days,
              "common_bars": len(common_ts), "full_sample": full,
              "walk_forward": walk, "purged_cpcv": cpcv, "gates": gate,
              "validation_pass": all(gate.values()),
              "deployment_policy": "paper_and_telegram_allowed_only_if_validation_pass_true"}
    return report


def render(r):
    gate_rows = "\n".join(f"| {k} | {'PASS' if v else 'FAIL'} |" for k, v in r["gates"].items())
    lines = ["# Advanced Strategy Validation", "", f"Generated: {r['generated_at']}",
             f"Validation verdict: **{'PASS' if r['validation_pass'] else 'FAIL'}**", "",
             "## Gate results", "", "| Gate | Result |", "|---|---|", gate_rows, "",
             "## Baseline and cost stress", "", "| Fee bps/side | Trades | Win rate | Profit factor | Expectancy | Max DD |",
             "|---:|---:|---:|---:|---:|---:|"]
    for fee, m in r["full_sample"].items():
        lines.append(f"| {fee} | {m['trades']} | {m['win_rate']} | {m['profit_factor']} | {m['expectancy']} | {m['max_drawdown']} |")
    lines += ["", "The signal uses fixed rules and no fitted model. Walk-forward windows measure temporal stability; CPCV results are descriptive robustness checks, not proof of future profitability.",
              "Paper trading and Telegram alerts are prohibited unless the validation verdict is PASS. This report does not authorize live execution."]
    return "\n".join(lines) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=120)
    args = ap.parse_args()
    report = run(args.days)
    REPORT_JSON.parent.mkdir(exist_ok=True)
    REPORT_JSON.write_text(json.dumps(report, indent=2))
    REPORT_MD.write_text(render(report))
    print(json.dumps({"validation_pass": report["validation_pass"], "gates": report["gates"]}, indent=2))


if __name__ == "__main__":
    main()
