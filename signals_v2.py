import math
import config_v2 as cfg


def _f(x, default=0.0):
    """Safe float extractor."""
    if x is None:
        return default
    try:
        v = float(x)
        return v if v == v else default
    except Exception:
        return default


def evaluate(row, extra, is_backtest=False):
    """
    SURGICAL TEST: শুধু res_sweep SELL in session
    বাকি সব setup বাদ — data-driven profitable bucket
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

    # ── Layer 1: ONLY res_sweep (SELL direction) ──────────────
    prior_low = _f(row.get("prior_low"))
    prior_high = _f(row.get("prior_high"))
    direction = None

    # 🔑 SURGICAL: শুধু res_sweep detect করি, SELL direction
    if _f(row.get("sweep_res")) and regime != "TREND_DOWN":
        score += 30; s_zone += 30
        direction = "SELL"; tags["zone"] = "res_sweep"

    # ❌ অন্য সব setup disable (breakout, sup_sweep, level_bounce)
    if direction is None:
        return None

    # ── Layer 2: Flow ─────────────────────────────────────────
    cvd_div = _f(row.get("cvd_div"))
    taker_ratio = _f(row.get("taker_ratio"), 0.5)

    if direction == "SELL" and cvd_div < -0.3:
        score += 10; s_flow += 10
        tags["cvd_div"] = True

    if direction == "SELL" and taker_ratio < 0.40:
        score += 5; s_flow += 5

    # ── Layer 3: Crowding ─────────────────────────────────────
    funding = _f(extra.get("funding"))
    oi_chg = _f(extra.get("oi_chg"))
    fdiv = _f(extra.get("funding_div"))
    fdivz = _f(extra.get("funding_div_z"))

    if direction == "SELL" and funding > 0.0005:
        score += 15; s_crowd += 15
        tags["fund_extreme"] = True
    elif direction == "SELL" and funding > 0:
        score += 8; s_crowd += 8

    if abs(oi_chg) > 0.03 and funding > 0:
        score += 5; s_crowd += 5
        tags["oi_squeeze"] = True

    if abs(fdiv) > cfg.DIV_THRESH and abs(fdivz) > cfg.DIV_Z_THRESH:
        if fdiv < 0:  # SELL aligned divergence
            score += cfg.DIV_BOOST; s_crowd += cfg.DIV_BOOST
            tags["funding_div"] = True

    # ── Layer 4: Session (required for res_sweep) ─────────────
    hour_utc = extra.get("hour_utc", 12)

    # 🔑 SURGICAL: res_sweep only in session (08-16 UTC)
    if not (8 <= hour_utc <= 16):
        return None  # Off-session res_sweep বাদ
    
    score += 10; s_gate += 10
    tags["session"] = "good"

    # TREND_UP-এ res_sweep counter-trend, penalty
    if regime == "TREND_UP":
        score -= 10; s_gate -= 10
        tags["counter_trend"] = True

    # High vol penalty
    if rv_pct > 0.9:
        score -= 10; s_gate -= 10
        tags["high_vol"] = True

    # ── Quality Gates ─────────────────────────────────────────
    if _f(row.get("vol_ratio"), 0) < cfg.VOL_CONFIRM_RATIO:
        return None
    if rv_pct < cfg.VOL_BAND_LOW or rv_pct > cfg.VOL_BAND_HIGH:
        return None

    # ── Final decision ────────────────────────────────────────
    min_score = cfg.MIN_SCORE_BACKTEST if is_backtest else cfg.MIN_SCORE_LIVE
    if score < min_score:
        return None

    # ── SL/TP ─────────────────────────────────────────────────
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
