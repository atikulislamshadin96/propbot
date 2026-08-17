import math
import config_v2 as cfg


def _f(x, default=0.0):
    """Safe float extractor — returns default on None/NaN."""
    if x is None:
        return default
    try:
        v = float(x)
        return v if v == v else default  # NaN check
    except Exception:
        return default


def evaluate(row, extra, is_backtest=False):
    """
    Evaluate a completed candle row + extra signals.
    Returns signal dict or None.
    
    4-Layer Scoring:
      Layer 1 (Market Map): sweep/breakout/bounce  — max 30 pts
      Layer 2 (Flow): CVD divergence + taker       — max 15 pts
      Layer 3 (Crowding): funding + OI + div       — max ~20 pts
      Layer 4 (Regime/Session): regime + session   — ±10 pts
    """
    score = 0
    s_gate = 0
    s_zone = 0
    s_flow = 0
    s_crowd = 0
    tags = {}

    px = _f(row.get("close"))
    if px <= 0:
        return None

    atr_val = _f(row.get("atr"))
    if atr_val <= 0:
        return None

    rsi_val = _f(row.get("rsi"), 50.0)
    adx_val = _f(row.get("adx"), 20.0)
    ema20 = _f(row.get("ema20"))
    ema50 = _f(row.get("ema50"))
    vol_ratio = _f(row.get("vol_ratio"), 1.0)
    rv_pct = _f(row.get("rv_pct"), 0.5)

    # ── Regime detection ──────────────────────────────────────
    if adx_val > 25 and ema20 > ema50:
        regime = "TREND_UP"
    elif adx_val > 25 and ema20 < ema50:
        regime = "TREND_DOWN"
    else:
        regime = "RANGE"
    tags["regime"] = regime

    # ── Layer 1: Market Map (max 30 pts) ──────────────────────
    prior_low = _f(row.get("prior_low"))
    prior_high = _f(row.get("prior_high"))
    direction = None

    # Sweep (liquidity grab with rejection)
    if _f(row.get("sweep_sup")) and regime != "TREND_UP":
        score += 30; s_zone += 30
        direction = "BUY"; tags["zone"] = "sup_sweep"
    elif _f(row.get("sweep_res")) and regime != "TREND_DOWN":
        score += 30; s_zone += 30
        direction = "SELL"; tags["zone"] = "res_sweep"

    # Breakout (trend continuation)
    if direction is None:
        if regime == "TREND_UP" and px > prior_high > 0:
            score += 25; s_zone += 25
            direction = "BUY"; tags["zone"] = "breakout"
        elif regime == "TREND_DOWN" and px < prior_low > 0:
            score += 25; s_zone += 25
            direction = "SELL"; tags["zone"] = "breakout"

    # Level bounce (RANGE only)
    if direction is None and regime == "RANGE":
        if prior_low > 0 and (px - prior_low) <= 0.3 * atr_val and rsi_val < 45:
            score += 10; s_zone += 10
            direction = "BUY"; tags["zone"] = "level_bounce"
        elif prior_high > 0 and (prior_high - px) <= 0.3 * atr_val and rsi_val > 55:
            score += 10; s_zone += 10
            direction = "SELL"; tags["zone"] = "level_bounce"

    if direction is None:
        return None

    # ── Layer 2: Flow (max 15 pts) ────────────────────────────
    cvd_div = _f(row.get("cvd_div"))
    taker_ratio = _f(row.get("taker_ratio"), 0.5)

    # CVD divergence
    if direction == "BUY" and cvd_div > 0.3:
        score += 10; s_flow += 10
        tags["cvd_div"] = True
    elif direction == "SELL" and cvd_div < -0.3:
        score += 10; s_flow += 10
        tags["cvd_div"] = True

    # Taker ratio alignment
    if direction == "BUY" and taker_ratio > 0.60:
        score += 5; s_flow += 5
    elif direction == "SELL" and taker_ratio < 0.40:
        score += 5; s_flow += 5

    # ── OPTION A: SOFT GATE (penalize in backtest, reject in live) ──
    # Live: Bybit/Binance data available → s_flow meaningful → hard gate
    # Backtest: US-blocked → s_flow often 0 → soft gate (penalize, don't reject)
    if cfg.OPTION_A_SOFT and is_backtest and s_flow < 5:
        score -= 10; s_gate -= 10
        tags["l2_missing"] = True
    elif not is_backtest and s_flow < 5:
        return None  # Live mode: hard reject

    # ── Layer 3: Crowding (max ~20 pts) ───────────────────────
    funding = _f(extra.get("funding"))
    oi_chg = _f(extra.get("oi_chg"))
    fdiv = _f(extra.get("funding_div"))
    fdivz = _f(extra.get("funding_div_z"))

    # Funding alignment
    if direction == "BUY" and funding < -0.0005:
        score += 15; s_crowd += 15
        tags["fund_extreme"] = True
    elif direction == "SELL" and funding > 0.0005:
        score += 15; s_crowd += 15
        tags["fund_extreme"] = True
    elif direction == "BUY" and funding < 0:
        score += 8; s_crowd += 8
    elif direction == "SELL" and funding > 0:
        score += 8; s_crowd += 8

    # OI squeeze
    if abs(oi_chg) > 0.03:
        if (direction == "BUY" and funding < 0) or (direction == "SELL" and funding > 0):
            score += 5; s_crowd += 5
            tags["oi_squeeze"] = True

    # Funding divergence
    if abs(fdiv) > cfg.DIV_THRESH and abs(fdivz) > cfg.DIV_Z_THRESH:
        if (direction == "BUY" and fdiv > 0) or (direction == "SELL" and fdiv < 0):
            score += cfg.DIV_BOOST; s_crowd += cfg.DIV_BOOST
            tags["funding_div"] = True

    # ── Layer 4: Regime/Session (±10 pts) ─────────────────────
    hour_utc = extra.get("hour_utc", 12)

    # Session bonus
    if 8 <= hour_utc <= 16:
        score += 10; s_gate += 10
        tags["session"] = "good"
    else:
        tags["session"] = "off"

    # ── OPTION G: sup_sweep BUY in session suppress ──
    if (tags.get("zone") == "sup_sweep" and direction == "BUY" 
        and 8 <= hour_utc <= 16):
        return None

    # Counter-trend penalty
    if tags.get("zone") == "sup_sweep" and regime == "TREND_DOWN":
        score -= 10; s_gate -= 10
        tags["counter_trend"] = True
    elif tags.get("zone") == "res_sweep" and regime == "TREND_UP":
        score -= 10; s_gate -= 10
        tags["counter_trend"] = True

    # High volatility penalty
    if rv_pct > 0.9:
        score -= 10; s_gate -= 10
        tags["high_vol"] = True

    # ── Quality-First Gates ───────────────────────────────────
    if _f(row.get("vol_ratio"), 0) < cfg.VOL_CONFIRM_RATIO:
        return None
    if rv_pct < cfg.VOL_BAND_LOW or rv_pct > cfg.VOL_BAND_HIGH:
        return None

    # ── Final decision (adaptive MIN_SCORE) ───────────────────
    min_score = cfg.MIN_SCORE_BACKTEST if is_backtest else cfg.MIN_SCORE_LIVE
    if score < min_score:
        return None

    # ── SL/TP calculation ─────────────────────────────────────
    if direction == "BUY":
        sl = px - cfg.SL_ATR * atr_val
        risk = px - sl
        tp = px + risk * cfg.TP_RR
    else:
        sl = px + cfg.SL_ATR * atr_val
        risk = sl - px
        tp = px - risk * cfg.TP_RR

    return {
        "side": direction,
        "entry": round(px, 6),
        "sl": round(sl, 6),
        "tp": round(tp, 6),
        "score": round(score, 2),
        "s_gate": round(s_gate, 2),
        "s_zone": round(s_zone, 2),
        "s_flow": round(s_flow, 2),
        "s_crowd": round(s_crowd, 2),
        "regime": regime,
        "tags": tags,
        "zone": tags.get("zone", ""),
    }
