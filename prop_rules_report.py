"""Generate the generic paper-only prop-rule status report."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import config_v2 as cfg
import paper_db as db
from paper_monitor import data_health
from prop_rules import evaluate, from_config
from risk_manager import max_drawdown_pct, consecutive_losses

JSON_PATH = Path("reports/prop_rules_latest.json")
MD_PATH = Path("reports/prop_rules_latest.md")


def _equity(closed: list[dict]) -> float:
    equity = float(cfg.PROP_INITIAL_EQUITY)
    for trade in sorted(closed, key=lambda item: item.get("closed_ts") or ""):
        equity *= 1.0 + float(trade.get("pnl_pct") or 0.0) / 100.0
    return equity


def run() -> dict:
    now = datetime.now(timezone.utc)
    closed = db.closed_trades()
    open_trades = db.open_trades()
    health = data_health(cfg.SYMBOLS, now)
    ages = [float(item.get("age_minutes", 1e9)) for item in health]
    data_ok = all(item.get("status") == "FRESH" for item in health)
    equity = _equity(closed)
    day_start = float(cfg.PROP_INITIAL_EQUITY)
    snapshot = {
        "equity": equity,
        "day_start_equity": day_start,
        "peak_equity": max(float(cfg.PROP_INITIAL_EQUITY), equity),
        "open_risk_pct": sum(float(item.get("risk_pct") or 0.0) for item in open_trades),
        "trades_today": len(db.trades_today()),
        "consecutive_losses": consecutive_losses(closed),
        "max_data_age_minutes": max(ages, default=1e9),
        "data_ok": data_ok,
    }
    decision = evaluate(snapshot, from_config(cfg))
    report = {
        "timestamp": now.isoformat(),
        "mode": "PAPER_ONLY",
        "active_program": cfg.ACTIVE_PROGRAM,
        "decision": decision,
        "data_health": health,
        "ledger": {
            "closed_trades": len(closed),
            "open_trades": len(open_trades),
            "equity_method": "initial_equity compounded by recorded paper pnl_pct",
        },
    }
    JSON_PATH.parent.mkdir(exist_ok=True)
    JSON_PATH.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    m = decision["metrics"]
    reasons = ", ".join(decision["reasons"]) if decision["reasons"] else "none"
    MD_PATH.write_text(
        f"""# Generic Prop-Rule Paper Report

Timestamp: `{report['timestamp']}`

Mode: **PAPER_ONLY**

Program: `{cfg.ACTIVE_PROGRAM}`

## Decision

| Field | Value |
|---|---|
| Status | `{decision['status']}` |
| Paper allowed | `{decision['allowed_for_paper']}` |
| Kill switch | `{decision['kill_switch']}` |
| Reasons | `{reasons}` |
| Target reached | `{decision['target_reached']}` |

## Metrics

| Measure | Value |
|---|---:|
| Equity proxy | `{m['equity']:.2f}` |
| Daily loss (%) | `{m['daily_loss_pct']:.4f}` |
| Total drawdown (%) | `{m['total_drawdown_pct']:.4f}` |
| Open risk (%) | `{m['open_risk_pct']:.4f}` |
| Trades today | `{m['trades_today']}` |
| Consecutive losses | `{m['consecutive_losses']}` |
| Maximum data age (minutes) | `{m['max_data_age_minutes']:.2f}` |

> These are generic paper-account checks. They are not a representation of a named prop firm’s current rulebook, and they cannot authorize live orders.
""", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return report


if __name__ == "__main__":
    run()
