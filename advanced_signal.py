"""Advanced non-retail signal engine.

Strategy: multi-asset aggressive-flow liquidity shock.

The signal uses taker-buy volume imbalance, abnormal volume, robust realized
range, and cross-asset flow breadth. It intentionally does not use RSI, EMA,
MACD, Bollinger bands, simple breakouts, candlestick patterns, funding
arbitrage, or cross-venue basis execution.

This module is deterministic and paper-only. It never submits orders.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from statistics import median
from typing import Any, Dict, Iterable, List, Optional, Sequence
import math


@dataclass(frozen=True)
class AdvancedSignalConfig:
    lookback: int = 96
    flow_window: int = 32
    range_window: int = 32
    volume_z_min: float = 1.5
    flow_abs_min: float = 0.20
    return_abs_min: float = 0.0015
    breadth_min: float = 0.67
    max_spread_proxy: float = 0.012
    stop_range_multiple: float = 1.60
    target_range_multiple: float = 2.80
    max_hold_bars: int = 16
    cooldown_bars: int = 8
    max_daily_signals: int = 3
    min_quality_score: float = 0.70


@dataclass(frozen=True)
class AdvancedSignal:
    symbol: str
    side: str
    signal_ts: int
    entry: float
    stop_loss: float
    take_profit: float
    risk_distance: float
    reward_risk: float
    quality_score: float
    flow_imbalance: float
    volume_z: float
    return_n: float
    range_scale: float
    breadth: float
    strategy: str = "aggressive_flow_liquidity_shock"
    mode: str = "paper"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _finite(x: Any) -> bool:
    try:
        return math.isfinite(float(x))
    except (TypeError, ValueError):
        return False


def _mean(xs: Sequence[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def _std(xs: Sequence[float]) -> float:
    if len(xs) < 2:
        return 0.0
    m = _mean(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (len(xs) - 1))


def _quantile(xs: Sequence[float], q: float) -> float:
    if not xs:
        return 0.0
    ys = sorted(xs)
    pos = (len(ys) - 1) * q
    lo, hi = int(pos), min(int(pos) + 1, len(ys) - 1)
    return ys[lo] + (ys[hi] - ys[lo]) * (pos - lo)


def _features(rows: Sequence[Dict[str, Any]], cfg: AdvancedSignalConfig) -> Optional[Dict[str, float]]:
    """Compute features ending at the last completed row without look-ahead."""
    if len(rows) < max(cfg.lookback, cfg.flow_window, cfg.range_window) + 2:
        return None
    clean = []
    for r in rows:
        try:
            close = float(r["close"])
            high = float(r["high"])
            low = float(r["low"])
            volume = float(r["volume"])
            taker = float(r["taker_buy"])
            ts = int(r["ts"])
            if not all(_finite(v) for v in (close, high, low, volume, taker)) or volume <= 0 or close <= 0:
                continue
            clean.append({"ts": ts, "close": close, "high": high, "low": low,
                          "volume": volume, "taker_buy": taker})
        except (KeyError, TypeError, ValueError):
            continue
    if len(clean) < cfg.lookback + 2:
        return None
    current = clean[-1]
    prior = clean[:-1]
    flow_hist = []
    vol_hist = []
    range_hist = []
    for i in range(max(1, len(prior) - cfg.lookback), len(prior)):
        p = prior[i]
        prev_close = prior[i - 1]["close"]
        flow_hist.append(2.0 * p["taker_buy"] / p["volume"] - 1.0)
        vol_hist.append(p["volume"])
        range_hist.append(max(p["high"] - p["low"], abs(p["high"] - prev_close), abs(p["low"] - prev_close)) / prev_close)
    current_flow = 2.0 * current["taker_buy"] / current["volume"] - 1.0
    recent_flow = flow_hist[-cfg.flow_window:]
    recent_vol = vol_hist[-cfg.flow_window:]
    recent_range = range_hist[-cfg.range_window:]
    flow_mean = _mean(recent_flow)
    volume_mean = _mean(recent_vol)
    volume_std = _std(recent_vol)
    volume_z = (current["volume"] - volume_mean) / volume_std if volume_std > 0 else 0.0
    prev_close = prior[-1]["close"]
    return_n = current["close"] / prev_close - 1.0
    range_scale = median(recent_range) if recent_range else 0.0
    spread_proxy = (current["high"] - current["low"]) / current["close"]
    # A signed flow impulse measures current aggressive pressure relative to
    # its trailing state; it is not a directional price-level rule.
    flow_impulse = current_flow - flow_mean
    return {
        "ts": float(current["ts"]),
        "close": current["close"],
        "flow": current_flow,
        "flow_impulse": flow_impulse,
        "volume_z": volume_z,
        "return_n": return_n,
        "range_scale": range_scale,
        "spread_proxy": spread_proxy,
    }


def _direction(f: Dict[str, float], cfg: AdvancedSignalConfig) -> Optional[str]:
    if f["volume_z"] < cfg.volume_z_min or abs(f["flow"]) < cfg.flow_abs_min:
        return None
    if abs(f["return_n"]) < cfg.return_abs_min:
        return None
    # Require price movement to agree with aggressive flow. This is an
    # information-arrival / liquidity-shock continuation setup, not a breakout.
    if f["flow"] * f["return_n"] <= 0:
        return None
    if f["spread_proxy"] > cfg.max_spread_proxy:
        return None
    return "LONG" if f["flow"] > 0 else "SHORT"


def _breadth(features: Dict[str, Dict[str, float]], direction: str) -> float:
    if not features:
        return 0.0
    signs = [1 if (f["flow"] > 0 if direction == "LONG" else f["flow"] < 0) else 0 for f in features.values()]
    return sum(signs) / len(signs)


def generate_signals(
    data: Dict[str, Sequence[Dict[str, Any]]],
    cfg: AdvancedSignalConfig = AdvancedSignalConfig(),
    now_ts: Optional[int] = None,
) -> List[AdvancedSignal]:
    """Generate at most one candidate per symbol, with cross-asset confirmation."""
    features = {}
    for symbol, rows in data.items():
        f = _features(rows, cfg)
        if f is not None:
            features[symbol] = f
    candidates: List[AdvancedSignal] = []
    for symbol, f in features.items():
        direction = _direction(f, cfg)
        if direction is None:
            continue
        breadth = _breadth(features, direction)
        if breadth < cfg.breadth_min:
            continue
        if f["range_scale"] <= 0:
            continue
        risk = f["range_scale"] * f["close"] * cfg.stop_range_multiple
        reward = f["range_scale"] * f["close"] * cfg.target_range_multiple
        if direction == "LONG":
            stop, target = f["close"] - risk, f["close"] + reward
        else:
            stop, target = f["close"] + risk, f["close"] - reward
        # Quality is a bounded combination of independent anomaly strengths.
        flow_component = min(1.0, abs(f["flow"]) / 0.80)
        volume_component = min(1.0, max(0.0, f["volume_z"]) / 4.0)
        breadth_component = min(1.0, breadth)
        quality = round(0.45 * flow_component + 0.30 * volume_component + 0.25 * breadth_component, 4)
        if quality < cfg.min_quality_score:
            continue
        candidates.append(AdvancedSignal(
            symbol=symbol,
            side=direction,
            signal_ts=int(f["ts"] if now_ts is None else now_ts),
            entry=round(f["close"], 8),
            stop_loss=round(stop, 8),
            take_profit=round(target, 8),
            risk_distance=round(risk, 8),
            reward_risk=round(reward / risk, 4),
            quality_score=quality,
            flow_imbalance=round(f["flow"], 6),
            volume_z=round(f["volume_z"], 4),
            return_n=round(f["return_n"], 6),
            range_scale=round(f["range_scale"], 8),
            breadth=round(breadth, 4),
        ))
    candidates.sort(key=lambda x: (-x.quality_score, x.symbol))
    return candidates[:cfg.max_daily_signals]


def evaluate_forward(signal: AdvancedSignal, future_rows: Sequence[Dict[str, Any]], fee_bps: float = 5.0) -> Dict[str, Any]:
    """Evaluate one signal on future bars only; conservative stop-first tie break."""
    side = 1 if signal.side == "LONG" else -1
    exit_price = None
    reason = "time"
    close_bar = None
    for i, row in enumerate(future_rows[:16]):
        high, low = float(row["high"]), float(row["low"])
        hit_stop = (low <= signal.stop_loss) if side == 1 else (high >= signal.stop_loss)
        hit_target = (high >= signal.take_profit) if side == 1 else (low <= signal.take_profit)
        if hit_stop:
            exit_price, reason, close_bar = signal.stop_loss, "stop", i
            break
        if hit_target:
            exit_price, reason, close_bar = signal.take_profit, "target", i
            break
    if exit_price is None and future_rows:
        exit_price = float(future_rows[min(15, len(future_rows) - 1)]["close"])
        close_bar = min(15, len(future_rows) - 1)
    if exit_price is None:
        return {"valid": False, "reason": "insufficient_future_bars"}
    gross = side * (exit_price - signal.entry) / signal.entry
    net = gross - 2.0 * fee_bps / 10000.0
    return {"valid": True, "symbol": signal.symbol, "side": signal.side,
            "signal_ts": signal.signal_ts, "close_bar": close_bar,
            "exit_price": exit_price, "reason": reason,
            "gross_return": gross, "net_return": net,
            "reward_risk": signal.reward_risk, "quality_score": signal.quality_score}
