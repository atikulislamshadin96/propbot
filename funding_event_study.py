"""Historical funding-divergence event study; a funding proxy, not a trading backtest."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

import config_v2 as cfg
from funding_data import normalized_funding_series
from funding_strategy import divergence_panel
from signals_v3 import signal_from_panel_row


REPORT_DIR = Path("reports")


def run_event_study(panel: pd.DataFrame) -> pd.DataFrame:
    """Evaluate non-overlapping events using only subsequently observed funding."""
    scored = divergence_panel(panel)
    records = []
    next_eligible = None
    for timestamp, row in scored.iterrows():
        if next_eligible is not None and timestamp < next_eligible:
            continue
        candidate = signal_from_panel_row({**row.to_dict(), "timestamp": timestamp}, coin=cfg.FUNDING_ACTIVE_COIN)
        if candidate is None:
            continue
        future = panel.loc[panel.index > timestamp, "hl_funding"] - panel.loc[panel.index > timestamp, "dydx_funding"]
        future = future.iloc[: cfg.FUNDING_EXPECTED_HOLD_HOURS]
        if len(future) < cfg.FUNDING_EXPECTED_HOLD_HOURS:
            continue
        direction = 1.0 if candidate["side"] == "SHORT_HL_LONG_DYDX" else -1.0
        realized_gross_bps = direction * float(future.sum()) * 10_000
        records.append(
            {
                "entry_time": timestamp,
                "entry_spread": float(row["spread"]),
                "entry_z": float(row["spread_z"]),
                "expected_gross_bps": float(candidate["expected_gross_bps"]),
                "fixed_cost_bps": float(candidate["required_cost_bps"]),
                "realized_funding_proxy_bps": realized_gross_bps - float(candidate["required_cost_bps"]),
                "funding_hours_observed": len(future),
                "side": candidate["side"],
            }
        )
        next_eligible = timestamp + pd.Timedelta(hours=cfg.FUNDING_EXPECTED_HOLD_HOURS)
    return pd.DataFrame(records)


def summarize(events: pd.DataFrame) -> dict:
    """Summarize event-study proxy returns without treating them as account PnL."""
    if events.empty:
        return {"events": 0, "positive_proxy_rate": None, "median_proxy_bps": None, "mean_proxy_bps": None}
    proxy = events["realized_funding_proxy_bps"]
    return {
        "events": int(len(events)),
        "positive_proxy_rate": float((proxy > 0).mean()),
        "median_proxy_bps": float(proxy.median()),
        "mean_proxy_bps": float(proxy.mean()),
        "sum_proxy_bps": float(proxy.sum()),
    }


def main():
    """Write a counterfactual event-study report from public funding data."""
    REPORT_DIR.mkdir(exist_ok=True)
    panel = normalized_funding_series(cfg.FUNDING_ACTIVE_COIN, cfg.FUNDING_HISTORY_DAYS)
    events = run_event_study(panel)
    summary = {
        "mode": "COUNTERFACTUAL_FUNDING_EVENT_STUDY_ONLY",
        "coin": cfg.FUNDING_ACTIVE_COIN,
        "history_days_requested": cfg.FUNDING_HISTORY_DAYS,
        "overlapping_hourly_observations": int(len(panel)),
        "entry_rule": f"|z| >= {cfg.FUNDING_Z_ENTRY}; expected gross funding over {cfg.FUNDING_EXPECTED_HOLD_HOURS}h >= {cfg.FUNDING_ROUNDTRIP_COST_BPS * cfg.FUNDING_COST_BUFFER:.1f} bps",
        "summary": summarize(events),
        "limitations": [
            "This is a funding-payment proxy and excludes basis movement, mark-price divergence, execution, borrow, margin, liquidation, settlement, and venue risk.",
            "It uses public hourly observations and does not prove tradability or capacity.",
            "No orders are sent and the output is not an investment recommendation.",
        ],
    }
    (REPORT_DIR / "funding_event_study_latest.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    events.to_csv(REPORT_DIR / "funding_event_study_events.csv", index=False)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
