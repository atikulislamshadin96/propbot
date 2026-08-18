"""Counterfactual funding-divergence backtest for research and paper validation."""
from __future__ import annotations

import numpy as np
import pandas as pd

import config_v2 as cfg
from funding_data import normalized_funding_series
from funding_strategy import divergence_panel
from signals_v3 import signal_from_panel_row


def run(coin: str = cfg.FUNDING_ACTIVE_COIN, days: int = cfg.FUNDING_HISTORY_DAYS) -> dict:
    """Generate non-overlapping divergence events from subsequent funding only."""
    panel = normalized_funding_series(coin, days=days)
    scored = divergence_panel(panel)
    events: list[dict] = []
    next_eligible = None
    for timestamp, row in scored.iterrows():
        if next_eligible is not None and timestamp < next_eligible:
            continue
        candidate = signal_from_panel_row({**row.to_dict(), "timestamp": timestamp}, coin=coin)
        if candidate is None:
            continue
        future = panel.loc[panel.index > timestamp, "hl_funding"] - panel.loc[panel.index > timestamp, "dydx_funding"]
        future = future.iloc[: cfg.FUNDING_EXPECTED_HOLD_HOURS]
        if len(future) < cfg.FUNDING_EXPECTED_HOLD_HOURS:
            continue
        direction = 1.0 if candidate["side"] == "SHORT_HL_LONG_DYDX" else -1.0
        realized_gross_bps = direction * float(future.sum()) * 10_000
        proxy_bps = realized_gross_bps - candidate["required_cost_bps"]
        open_bar = int(panel.index.get_indexer([timestamp])[0])
        events.append(
            {
                **candidate,
                "entry_time": timestamp.isoformat(),
                "exit_time": (timestamp + pd.Timedelta(hours=cfg.FUNDING_EXPECTED_HOLD_HOURS)).isoformat(),
                "open_bar": open_bar,
                "close_bar": open_bar + cfg.FUNDING_EXPECTED_HOLD_HOURS,
                "realized_gross_bps": realized_gross_bps,
                "proxy_pnl_bps": proxy_bps,
                "funding_hours_observed": len(future),
            }
        )
        next_eligible = timestamp + pd.Timedelta(hours=cfg.FUNDING_EXPECTED_HOLD_HOURS)
    return {"coin": coin, "days": days, "panel": panel, "events": events}


def metrics(events: list[dict]) -> dict:
    """Calculate funding-proxy metrics, returning null-like values when empty."""
    if not events:
        return {"events": 0, "win_rate_pct": None, "expectancy_bps": None, "net_bps": None, "profit_factor": None}
    pnls = np.array([float(event["proxy_pnl_bps"]) for event in events])
    wins = pnls[pnls > 0]
    losses = pnls[pnls <= 0]
    gross_loss = abs(float(losses.sum()))
    return {
        "events": int(len(pnls)),
        "win_rate_pct": round(float((pnls > 0).mean() * 100), 2),
        "expectancy_bps": round(float(pnls.mean()), 4),
        "net_bps": round(float(pnls.sum()), 4),
        "profit_factor": round(float(wins.sum() / gross_loss), 4) if gross_loss else None,
    }


def monte_carlo(events: list[dict], sims: int = 2000, ruin_dd: float = 0.10) -> dict:
    """Estimate path-order sensitivity on proxy bps, not account-level trading risk."""
    if len(events) < 2:
        return {"simulations": 0, "median_final_multiple": None, "ruin_probability_pct": None}
    source = np.array([float(event["proxy_pnl_bps"]) for event in events])
    finals = []
    ruins = 0
    rng = np.random.default_rng(7)
    for _ in range(sims):
        sample = rng.permutation(source)
        equity = np.cumprod(1.0 + sample / 10_000.0)
        peak = np.maximum.accumulate(equity)
        if np.min((equity - peak) / peak) <= -ruin_dd:
            ruins += 1
        finals.append(float(equity[-1]))
    return {
        "simulations": sims,
        "median_final_multiple": round(float(np.median(finals)), 6),
        "ruin_probability_pct": round(100.0 * ruins / sims, 3),
    }
