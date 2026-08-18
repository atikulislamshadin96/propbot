"""Paper-portfolio risk controls and fail-closed circuit breakers."""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Any, Iterable, Mapping

import config_v2 as cfg


def _parse_ts(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def _today(value: Any, now: datetime) -> bool:
    parsed = _parse_ts(value)
    return parsed is not None and parsed.astimezone(timezone.utc).date() == now.astimezone(timezone.utc).date()


def equity_curve(closed_trades: Iterable[Mapping[str, Any]]) -> list[float]:
    equity = 1.0
    curve = []
    for trade in sorted(closed_trades, key=lambda item: str(item.get("closed_ts") or item.get("ts") or "")):
        pnl_pct = float(trade.get("pnl_pct") or 0.0)
        equity *= 1.0 + pnl_pct / 100.0
        curve.append(equity)
    return curve


def max_drawdown_pct(closed_trades: Iterable[Mapping[str, Any]]) -> float:
    curve = equity_curve(closed_trades)
    if not curve:
        return 0.0
    peak = 1.0
    worst = 0.0
    for value in curve:
        peak = max(peak, value)
        worst = min(worst, (value - peak) / peak * 100.0)
    return worst


def consecutive_losses(closed_trades: Iterable[Mapping[str, Any]]) -> int:
    ordered = sorted(closed_trades, key=lambda item: str(item.get("closed_ts") or item.get("ts") or ""))
    count = 0
    for trade in reversed(ordered):
        if float(trade.get("pnl_pct") or 0.0) < 0:
            count += 1
        else:
            break
    return count


def _candidate_risk_pct(candidate: Mapping[str, Any]) -> float:
    value = float(candidate.get("risk_pct") or cfg.MAX_RISK_PCT)
    return max(0.0, min(value, cfg.MAX_RISK_PCT))


def assess_candidate(
    candidate: Mapping[str, Any],
    *,
    open_trades: Iterable[Mapping[str, Any]],
    closed_trades: Iterable[Mapping[str, Any]],
    all_trades: Iterable[Mapping[str, Any]] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Return an auditable allow/deny decision; deny on missing or unsafe state."""
    now = now or datetime.now(timezone.utc)
    open_list = list(open_trades)
    closed_list = list(closed_trades)
    all_list = list(all_trades) if all_trades is not None else open_list + closed_list
    reasons: list[str] = []
    risk_pct = _candidate_risk_pct(candidate)
    symbol = str(candidate.get("symbol") or candidate.get("coin") or "")

    if candidate.get("mode") not in {"PAPER_ONLY", "RESEARCH_ONLY_RELAXED"}:
        reasons.append("unsupported_or_live_mode")
    if not symbol:
        reasons.append("missing_symbol")
    if len(open_list) >= cfg.MAX_POSITIONS:
        reasons.append("max_positions")
    if symbol and any(str(trade.get("symbol") or trade.get("coin") or "") == symbol for trade in open_list):
        reasons.append("duplicate_symbol")
    opened_today = sum(1 for trade in all_list if _today(trade.get("ts"), now))
    if opened_today >= cfg.MAX_TRADES_DAY:
        reasons.append("max_trades_day")

    daily_pnl = sum(float(trade.get("pnl_pct") or 0.0) for trade in closed_list if _today(trade.get("closed_ts"), now))
    daily_limit = float(cfg.P["daily_loss_pct"]) * float(cfg.CIRCUIT_BREAKER_BUFFER)
    if daily_pnl <= -daily_limit:
        reasons.append("daily_loss_circuit_breaker")

    drawdown = max_drawdown_pct(closed_list)
    total_limit = float(cfg.P["total_dd_pct"]) * float(cfg.CIRCUIT_BREAKER_BUFFER)
    if drawdown <= -total_limit:
        reasons.append("total_drawdown_circuit_breaker")

    losses = consecutive_losses(closed_list)
    if losses >= cfg.MAX_CONSECUTIVE_LOSSES:
        reasons.append("consecutive_loss_circuit_breaker")

    open_risk = sum(_candidate_risk_pct(trade) for trade in open_list)
    if open_risk + risk_pct > cfg.MAX_PORTFOLIO_RISK_PCT:
        reasons.append("portfolio_risk_cap")

    latest_closed = max((_parse_ts(trade.get("closed_ts")) for trade in closed_list), default=None)
    if latest_closed is not None and now - latest_closed < timedelta(minutes=cfg.RISK_COOLDOWN_MINUTES):
        reasons.append("cooldown")

    return {
        "mode": "PAPER_ONLY",
        "allowed": not reasons,
        "symbol": symbol,
        "candidate_risk_pct": risk_pct,
        "open_positions": len(open_list),
        "open_risk_pct": round(open_risk, 6),
        "daily_pnl_pct": round(daily_pnl, 6),
        "max_drawdown_pct": round(drawdown, 6),
        "consecutive_losses": losses,
        "opened_today": opened_today,
        "reasons": reasons,
    }
