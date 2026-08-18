"""Forward-only backtest for the advanced aggressive-flow strategy."""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from advanced_data import fetch_symbol_panel
from advanced_signal import AdvancedSignalConfig, generate_signals, evaluate_forward

SYMBOLS = ("BTCUSDT", "ETHUSDT", "SOLUSDT")
REPORT_JSON = Path("reports/advanced_backtest_latest.json")
REPORT_MD = Path("reports/advanced_backtest_latest.md")


def metrics(trades: List[dict]) -> dict:
    if not trades:
        return {"trades": 0, "win_rate": None, "profit_factor": None,
                "expectancy": None, "net_return": 0.0, "max_drawdown": 0.0}
    vals = [float(t["net_return"]) for t in trades]
    wins = [v for v in vals if v > 0]
    losses = [v for v in vals if v < 0]
    equity, peak, max_dd = 1.0, 1.0, 0.0
    for v in vals:
        equity *= 1.0 + v
        peak = max(peak, equity)
        max_dd = min(max_dd, equity / peak - 1.0)
    gross_profit = sum(wins)
    gross_loss = abs(sum(losses))
    return {"trades": len(vals),
            "win_rate": round(len(wins) / len(vals), 6),
            "profit_factor": round(gross_profit / gross_loss, 6) if gross_loss else None,
            "expectancy": round(sum(vals) / len(vals), 8),
            "net_return": round(equity - 1.0, 6),
            "max_drawdown": round(max_dd, 6),
            "avg_win": round(sum(wins) / len(wins), 8) if wins else None,
            "avg_loss": round(sum(losses) / len(losses), 8) if losses else None}


def simulate_panel(panel: Dict[str, List[dict]], cfg: AdvancedSignalConfig,
                   fee_bps: float = 5.0, start_ts: Optional[int] = None,
                   end_ts: Optional[int] = None) -> List[dict]:
    symbols = tuple(panel)
    lengths = [len(panel[s]) for s in symbols]
    common_ts = sorted(set.intersection(*(set(int(r["ts"]) for r in panel[s]) for s in symbols)))
    if start_ts is not None:
        common_ts = [t for t in common_ts if t >= start_ts]
    if end_ts is not None:
        common_ts = [t for t in common_ts if t < end_ts]
    by_symbol = {s: {int(r["ts"]): r for r in panel[s]} for s in symbols}
    if not common_ts:
        return []
    trades: List[dict] = []
    last_signal_idx = defaultdict(lambda: -10_000)
    day_counts = defaultdict(int)
    # Warm-up bars are recovered from the full panel before the test window.
    full_ts = sorted(set.intersection(*(set(int(r["ts"]) for r in panel[s]) for s in symbols)))
    first_ts = common_ts[0]
    first_idx = full_ts.index(first_ts)
    for local_idx, ts in enumerate(common_ts):
        full_idx = first_idx + local_idx
        if full_idx < cfg.lookback + 2 or full_idx >= len(full_ts) - cfg.max_hold_bars - 1:
            continue
        dt = datetime.fromtimestamp(ts / 1000, tz=timezone.utc)
        day = dt.date().isoformat()
        window_start = max(0, full_idx + 1 - cfg.lookback - 2)
        window_ts = full_ts[window_start:full_idx + 1]
        data = {s: [by_symbol[s][t] for t in window_ts if t in by_symbol[s]] for s in symbols}
        signals = generate_signals(data, cfg, now_ts=ts)
        for signal in signals:
            if day_counts[day] >= cfg.max_daily_signals:
                break
            if local_idx - last_signal_idx[signal.symbol] < cfg.cooldown_bars:
                continue
            future = [by_symbol[signal.symbol][t] for t in full_ts[full_idx + 1:full_idx + 1 + cfg.max_hold_bars]
                      if t in by_symbol[signal.symbol]]
            result = evaluate_forward(signal, future, fee_bps=fee_bps)
            if not result.get("valid"):
                continue
            result.update({"symbol": signal.symbol, "signal_ts": ts,
                           "open_bar": full_idx, "strategy": signal.strategy,
                           "entry": signal.entry, "stop_loss": signal.stop_loss,
                           "take_profit": signal.take_profit,
                           "flow_imbalance": signal.flow_imbalance,
                           "volume_z": signal.volume_z,
                           "breadth": signal.breadth})
            trades.append(result)
            day_counts[day] += 1
            last_signal_idx[signal.symbol] = local_idx
    return trades


def run(days=120, cfg=None, fee_bps=5.0):
    cfg = cfg or AdvancedSignalConfig()
    panel = fetch_symbol_panel(SYMBOLS, interval="15m", days=days)
    lengths = [len(v) for v in panel.values()]
    if min(lengths or [0]) < cfg.lookback + 20:
        raise RuntimeError(f"insufficient historical data: {lengths}")
    trades = simulate_panel(panel, cfg, fee_bps=fee_bps)
    report = {"strategy": "aggressive_flow_liquidity_shock",
              "data_source": "Binance Vision spot klines",
              "symbols": list(SYMBOLS), "interval": "15m", "days_requested": days,
              "bars_common": len(set.intersection(*(set(int(r["ts"]) for r in panel[s]) for s in SYMBOLS))),
              "bars_by_symbol": dict(zip(SYMBOLS, lengths)),
              "fee_bps_per_side": fee_bps,
              "config": {k: getattr(cfg, k) for k in cfg.__dataclass_fields__},
              "metrics": metrics(trades), "trades": trades,
              "generated_at": datetime.now(timezone.utc).isoformat()}
    return report


def render(report):
    m = report["metrics"]
    lines = ["# Advanced Flow-Shock Backtest", "",
             f"Generated: {report['generated_at']}",
             f"Data: {report['data_source']}; symbols: {', '.join(report['symbols'])}; interval: {report['interval']}",
             "", "## Results", "", "| Metric | Value |", "|---|---:|",
             f"| Trades | {m['trades']} |", f"| Win rate | {m['win_rate']} |",
             f"| Profit factor | {m['profit_factor']} |", f"| Expectancy / trade | {m['expectancy']} |",
             f"| Net return | {m['net_return']} |", f"| Max drawdown | {m['max_drawdown']} |", "",
             "This is a research backtest using spot-candle taker-buy volume as a public order-flow proxy. It is not a fill simulation and does not authorize live trading."]
    return "\n".join(lines) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=120)
    ap.add_argument("--fee-bps", type=float, default=5.0)
    args = ap.parse_args()
    report = run(args.days, fee_bps=args.fee_bps)
    REPORT_JSON.parent.mkdir(exist_ok=True)
    REPORT_JSON.write_text(json.dumps(report, indent=2))
    REPORT_MD.write_text(render(report))
    print(json.dumps(report["metrics"], indent=2))


if __name__ == "__main__":
    main()
