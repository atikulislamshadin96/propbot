"""Forward-only backtest for the independent single-leg portfolio components.

This module is research infrastructure. It does not model exchange execution,
liquidation, leverage, borrow, funding, or prop-firm account rules.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Callable

import numpy as np

import config_v2 as cfg
from backtest_v2 import capped_stop_distance, fetch_range
from features import compute_features
from strategy_portfolio import mean_reversion_candidate, trend_following_candidate
from regime_filter import classify_regime, strategy_allowed

REPORT_PATH = Path("reports/portfolio_backtest_latest.json")
MAX_HOLD_BARS = 32


def _close_position(position: dict, price: float, reason: str, exit_index: int | None = None) -> dict:
    if position["side"] == "BUY":
        gross = (price - position["entry"]) / position["entry"] * 100.0
    else:
        gross = (position["entry"] - price) / position["entry"] * 100.0
    pnl = gross - cfg.FEE_PCT
    return {
        **position,
        "exit": float(price),
        "exit_reason": reason,
        "pnl_pct": float(pnl),
        "close_index": exit_index,
        "open_bar": int(position.get("open_index", position.get("signal_index", 0))),
        "close_bar": int(exit_index if exit_index is not None else position.get("open_index", 0)),
    }


def _metrics(trades: list[dict]) -> dict:
    if not trades:
        return {"trades": 0, "win_rate_pct": None, "profit_factor": None, "max_dd_pct": None, "expectancy_pct": None}
    pnls = np.asarray([trade["pnl_pct"] for trade in trades], dtype=float)
    wins = pnls[pnls > 0]
    losses = pnls[pnls <= 0]
    gross_wins = float(wins.sum())
    gross_losses = float(abs(losses.sum()))
    equity = np.cumprod(1.0 + pnls / 100.0)
    peaks = np.maximum.accumulate(equity)
    max_dd = float(np.min((equity - peaks) / peaks) * 100.0)
    return {
        "trades": int(len(pnls)),
        "win_rate_pct": round(float((pnls > 0).mean() * 100.0), 2),
        "profit_factor": round(gross_wins / gross_losses, 4) if gross_losses else None,
        "max_dd_pct": round(max_dd, 4),
        "expectancy_pct": round(float(pnls.mean()), 5),
        "net_pct": round(float(pnls.sum()), 4),
    }


def run_strategy(
    symbol: str,
    days: int,
    strategy_name: str,
    builder: Callable[[dict], dict | None],
    *,
    regime_aware: bool = False,
) -> dict:
    frame = fetch_range(symbol, cfg.INTERVAL, days)
    if frame.empty:
        return {"symbol": symbol, "strategy": strategy_name, "bars": 0, "metrics": _metrics([]), "trades": []}
    frame = compute_features(frame)
    trades: list[dict] = []
    open_position: dict | None = None
    for index in range(60, len(frame) - 1):
        candle = frame.iloc[index]
        if open_position is not None:
            exit_price = None
            exit_reason = None
            if open_position["side"] == "BUY":
                if float(candle["low"]) <= open_position["sl"]:
                    exit_price, exit_reason = open_position["sl"], "stop"
                elif float(candle["high"]) >= open_position["tp"]:
                    exit_price, exit_reason = open_position["tp"], "take_profit"
            else:
                if float(candle["high"]) >= open_position["sl"]:
                    exit_price, exit_reason = open_position["sl"], "stop"
                elif float(candle["low"]) <= open_position["tp"]:
                    exit_price, exit_reason = open_position["tp"], "take_profit"
            if exit_price is None and index - open_position["open_index"] >= MAX_HOLD_BARS:
                exit_price, exit_reason = float(candle["close"]), "time_exit"
            if exit_price is not None:
                trades.append(_close_position(open_position, exit_price, exit_reason, index))
                open_position = None

        if open_position is None:
            candle_data = candle.to_dict()
            candidate = builder(candle_data)
            if candidate is None:
                continue
            if regime_aware:
                regime = classify_regime(candle_data)
                allowed, _ = strategy_allowed(strategy_name, candidate, regime)
                if not allowed:
                    continue
            next_candle = frame.iloc[index + 1]
            entry = float(next_candle["open"])
            distance = capped_stop_distance(float(candidate["atr"]), entry)
            if distance <= 0:
                continue
            if candidate["side"] == "BUY":
                stop = entry - distance
                target = entry + distance * cfg.TP_RR
            else:
                stop = entry + distance
                target = entry - distance * cfg.TP_RR
            open_position = {
                "symbol": symbol,
                "strategy": strategy_name,
                "side": candidate["side"],
                "signal_index": index,
                "open_index": index + 1,
                "entry": entry,
                "sl": stop,
                "tp": target,
            }

    if open_position is not None:
        trades.append(_close_position(open_position, float(frame.iloc[-1]["close"]), "end_of_sample", len(frame) - 1))
    return {
        "symbol": symbol,
        "strategy": strategy_name,
        "regime_aware": regime_aware,
        "bars": int(len(frame)),
        "metrics": _metrics(trades),
        "trades": trades,
    }


def run(symbols: list[str] | None = None, days: int = 90, regime_aware: bool = False) -> dict:
    symbols = symbols or cfg.SYMBOLS
    builders = {
        "trend_following": trend_following_candidate,
        "mean_reversion": mean_reversion_candidate,
    }
    by_strategy: dict[str, list[dict]] = {name: [] for name in builders}
    for symbol in symbols:
        for name, builder in builders.items():
            by_strategy[name].append(run_strategy(symbol, days, name, builder, regime_aware=regime_aware))

    summary = {}
    for name, results in by_strategy.items():
        all_trades = [trade for result in results for trade in result["trades"]]
        summary[name] = {
            "symbols": [result["symbol"] for result in results],
            "bars": sum(result["bars"] for result in results),
            "metrics": _metrics(all_trades),
            "per_symbol": [{"symbol": r["symbol"], "metrics": r["metrics"]} for r in results],
        }
    output = {
        "mode": "RESEARCH_ONLY_FORWARD_BACKTEST",
        "regime_aware": regime_aware,
        "days": days,
        "symbols": symbols,
        "max_hold_bars": MAX_HOLD_BARS,
        "interval": cfg.INTERVAL,
        "fee_pct_per_completed_trade": cfg.FEE_PCT,
        "stop_model": "ATR distance capped by MAX_RISK_PCT; conservative stop-first ordering when both barriers touch",
        "strategies": summary,
        "limitations": [
            "No live orders, leverage, liquidation, borrow, funding payments, or venue outages are modeled.",
            "The metrics are historical estimates and do not establish future profitability or challenge-passing ability.",
            "The funding-divergence strategy is not included because its paired cross-venue payoff requires a separate basis-aware simulator.",
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
    run(args.symbols, args.days, regime_aware=args.regime_aware)
