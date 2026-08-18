"""Generic paper-only prop-firm rule evaluator.

Firm rules differ materially. This module intentionally uses configurable
parameters and never sends orders or claims that a particular firm's rules
are represented accurately.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Iterable


@dataclass(frozen=True)
class PropRules:
    initial_equity: float = 100_000.0
    daily_loss_limit_pct: float = 5.0
    total_drawdown_limit_pct: float = 10.0
    profit_target_pct: float = 10.0
    max_open_risk_pct: float = 1.0
    max_daily_trades: int = 3
    max_consecutive_losses: int = 3
    stale_data_limit_minutes: float = 30.0


def _pct(value: float, denominator: float) -> float:
    return (float(value) / float(denominator) * 100.0) if denominator else 0.0


def evaluate(snapshot: dict, rules: PropRules | None = None) -> dict:
    rules = rules or PropRules()
    equity = float(snapshot.get("equity", rules.initial_equity))
    day_start_equity = float(snapshot.get("day_start_equity", rules.initial_equity))
    peak_equity = float(snapshot.get("peak_equity", max(rules.initial_equity, equity)))
    daily_pnl = equity - day_start_equity
    total_pnl = equity - rules.initial_equity
    peak_drawdown = max(0.0, _pct(peak_equity - equity, peak_equity))
    initial_drawdown = max(0.0, _pct(rules.initial_equity - equity, rules.initial_equity))
    total_drawdown = max(peak_drawdown, initial_drawdown)
    daily_loss = max(0.0, _pct(-daily_pnl, day_start_equity))
    open_risk = float(snapshot.get("open_risk_pct", 0.0))
    trades_today = int(snapshot.get("trades_today", 0))
    consecutive_losses = int(snapshot.get("consecutive_losses", 0))
    data_age = float(snapshot.get("max_data_age_minutes", 0.0))
    data_ok = bool(snapshot.get("data_ok", True))
    reasons: list[str] = []
    if daily_loss >= rules.daily_loss_limit_pct:
        reasons.append("daily_loss_limit_breached")
    if total_drawdown >= rules.total_drawdown_limit_pct:
        reasons.append("total_drawdown_limit_breached")
    if open_risk > rules.max_open_risk_pct:
        reasons.append("open_risk_limit_breached")
    if trades_today >= rules.max_daily_trades:
        reasons.append("daily_trade_limit_reached")
    if consecutive_losses >= rules.max_consecutive_losses:
        reasons.append("consecutive_loss_lockout")
    if not data_ok or data_age > rules.stale_data_limit_minutes:
        reasons.append("data_freshness_failed")
    target_reached = total_pnl >= rules.initial_equity * rules.profit_target_pct / 100.0
    status = "TARGET_REACHED" if target_reached and not reasons else ("BLOCKED" if reasons else "ACTIVE_PAPER")
    return {
        "mode": "PAPER_ONLY",
        "status": status,
        "allowed_for_paper": not bool(reasons),
        "kill_switch": bool(reasons),
        "reasons": reasons,
        "target_reached": target_reached,
        "metrics": {
            "equity": round(equity, 4),
            "daily_loss_pct": round(daily_loss, 5),
            "total_drawdown_pct": round(total_drawdown, 5),
            "open_risk_pct": round(open_risk, 5),
            "trades_today": trades_today,
            "consecutive_losses": consecutive_losses,
            "max_data_age_minutes": round(data_age, 3),
        },
        "rules": asdict(rules),
        "limitations": [
            "Generic defaults are not a representation of any named firm’s current rulebook.",
            "This evaluator is a paper-account gate only and cannot submit or manage orders.",
            "Equity and risk inputs must come from a verified ledger before challenge use.",
        ],
    }


def from_config(cfg) -> PropRules:
    return PropRules(
        initial_equity=float(cfg.PROP_INITIAL_EQUITY),
        daily_loss_limit_pct=float(cfg.DAILY_LOSS_PCT),
        total_drawdown_limit_pct=float(cfg.TOTAL_DD_PCT),
        profit_target_pct=float(cfg.PROP_PROFIT_TARGET_PCT),
        max_open_risk_pct=float(cfg.PROP_MAX_OPEN_RISK_PCT),
        max_daily_trades=int(cfg.MAX_TRADES_DAY),
        max_consecutive_losses=int(cfg.MAX_CONSECUTIVE_LOSSES),
        stale_data_limit_minutes=float(cfg.PROP_DATA_STALE_LIMIT_MINUTES),
    )
