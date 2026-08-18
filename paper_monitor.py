"""Read-only paper-trading and data-quality monitor.

No orders are sent. Any execution-quality number is explicitly a paper proxy,
not an observed exchange fill.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import config_v2 as cfg
import paper_db as db
from binance_data import klines
from risk_manager import consecutive_losses, max_drawdown_pct

JSON_PATH = Path("reports/paper_monitor_latest.json")
MD_PATH = Path("reports/paper_monitor_latest.md")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _ts_to_dt(ts: int | float) -> datetime:
    value = float(ts)
    if value > 10_000_000_000:
        value /= 1000.0
    return datetime.fromtimestamp(value, tz=timezone.utc)


def _parse(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def data_health(symbols: list[str], now: datetime) -> list[dict]:
    rows = []
    for symbol in symbols:
        try:
            candles = klines(symbol, cfg.INTERVAL, 2)
            if len(candles) < 2:
                raise ValueError("fewer than two candles returned")
            completed = candles[-2]
            candle_ts = _ts_to_dt(completed["ts"])
            age_minutes = max(0.0, (now - candle_ts).total_seconds() / 60.0)
            rows.append({
                "symbol": symbol,
                "status": "FRESH" if age_minutes <= 30 else "STALE",
                "completed_candle_ts": candle_ts.isoformat(),
                "age_minutes": round(age_minutes, 2),
                "bars_received": len(candles),
                "error": None,
            })
        except Exception as exc:
            rows.append({"symbol": symbol, "status": "ERROR", "error": str(exc)})
    return rows


def execution_quality(trades: list[dict]) -> dict:
    opened = [trade for trade in trades if trade.get("status") == "open" or trade.get("closed_ts")]
    closed = [trade for trade in trades if trade.get("status") in {"tp", "sl"}]
    lags = []
    holding_minutes = []
    for trade in opened:
        opened_at = _parse(trade.get("ts"))
        signal_at = _parse(trade.get("signal_ts"))
        if opened_at and signal_at:
            lags.append(max(0.0, (opened_at - signal_at).total_seconds() / 60.0))
    for trade in closed:
        opened_at = _parse(trade.get("ts"))
        closed_at = _parse(trade.get("closed_ts"))
        if opened_at and closed_at:
            holding_minutes.append(max(0.0, (closed_at - opened_at).total_seconds() / 60.0))
    return {
        "paper_trades_observed": len(opened),
        "closed_trades_observed": len(closed),
        "median_signal_to_paper_open_minutes": round(float(sorted(lags)[len(lags) // 2]), 3) if lags else None,
        "median_paper_holding_minutes": round(float(sorted(holding_minutes)[len(holding_minutes) // 2]), 3) if holding_minutes else None,
        "observed_exchange_slippage_bps": None,
        "fill_quality_status": "UNOBSERVED_PAPER_PROXY_ONLY",
        "note": "Paper entries are assumptions; no exchange fills or order-book slippage are available.",
    }


def render_markdown(report: dict) -> str:
    health = report["data_health"]
    health_rows = "\n".join(
        f"| {item['symbol']} | {item['status']} | {item.get('age_minutes', 'n/a')} | {item.get('error') or '—'} |"
        for item in health
    )
    summary = report["summary"]
    quality = report["execution_quality"]
    return f"""# Paper Monitor Report

Timestamp: `{report['timestamp']}`  
Mode: **{report['mode']}**

## Data Health

| Symbol | Status | Completed-candle age (minutes) | Error |
|---|---|---:|---|
{health_rows}

## Paper Account Summary

| Measure | Value |
|---|---:|
| Open positions | {summary['open_positions']} |
| Closed trades | {summary['closed_trades']} |
| Daily PnL proxy (%) | {summary['daily_pnl_pct']:.4f} |
| Max drawdown proxy (%) | {summary['max_drawdown_pct']:.4f} |
| Consecutive losses | {summary['consecutive_losses']} |

## Execution-Quality Proxies

| Measure | Value |
|---|---:|
| Paper trades observed | {quality['paper_trades_observed']} |
| Median signal-to-paper-open (minutes) | {quality['median_signal_to_paper_open_minutes'] if quality['median_signal_to_paper_open_minutes'] is not None else 'n/a'} |
| Median paper holding time (minutes) | {quality['median_paper_holding_minutes'] if quality['median_paper_holding_minutes'] is not None else 'n/a'} |
| Observed exchange slippage (bps) | n/a |
| Fill status | {quality['fill_quality_status']} |

> This monitor is read-only. It cannot send orders, and its paper results do not establish live execution quality or challenge-passing ability.
"""


def run(symbols: list[str] | None = None) -> dict:
    now = _now()
    symbols = symbols or cfg.SYMBOLS
    closed = db.closed_trades()
    open_list = db.open_trades()
    all_list = db.all_trades()
    report = {
        "mode": "PAPER_ONLY_READ_ONLY",
        "timestamp": now.isoformat(),
        "data_health": data_health(symbols, now),
        "summary": {
            "open_positions": len(open_list),
            "closed_trades": len(closed),
            "daily_pnl_pct": round(db.daily_pnl_pct(), 6),
            "max_drawdown_pct": round(max_drawdown_pct(closed), 6),
            "consecutive_losses": consecutive_losses(closed),
        },
        "execution_quality": execution_quality(all_list),
        "limitations": [
            "No live exchange orders or fills are observed.",
            "Paper slippage is not a realized execution measurement.",
            "A stale or failed public-data check should block promotion and trigger review.",
        ],
    }
    JSON_PATH.parent.mkdir(exist_ok=True)
    JSON_PATH.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    MD_PATH.write_text(render_markdown(report), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbols", nargs="+", default=cfg.SYMBOLS)
    args = parser.parse_args()
    run(args.symbols)
