import config_v2 as cfg
from utils import _f


def _flow_score(row, direction):
    """Layer 2: Single composite flow score (max 15 points)
    CVD divergence + Taker ratio — VPIN-proxy dropped (mislabeled noise)
    """
    flow_points = 0.0
    tags = {}

    # ── CVD Divergence (0-10 points) ─────────────────────────
    px_12 = _f(row.get("px_12"))
    cvd_12 = _f(row.get("cvd_12"))
    if px_12 > 0:
        bull_div = row["close"] < px_12 and _f(row.get("cvd")) > cvd_12
        bear_div = row["close"] > px_12 and _f(row.get("cvd")) < cvd_12
        if direction == "BUY" and bull_div:
            flow_points += 10.0
            tags["flow_cvd_div"] = "bull"
        elif direction == "SELL" and bear_div:
            flow_points += 10.0
            tags["flow_cvd_div"] = "bear"

    # ── Taker Ratio Alignment (0-5 points) ───────────────────
    taker = _f(row.get("taker"), 0.5)
    if direction == "BUY":
        if taker > 0.60:
            flow_points += 5.0
            tags["flow_taker"] = "strong"
        elif taker > 0.55:
            flow_points += 3.0
            tags["flow_taker"] = "moderate"
    elif direction == "SELL":
        if taker < 0.40:
            flow_points += 5.0
            tags["flow_taker"] = "strong"
        elif taker < 0.45:
            flow_points += 3.0
            tags["flow_taker"] = "moderate"

    return flow_points, tags


def evaluate(row, extra):
    """Generate signal score. Returns dict or None if below MIN_SCORE."""
    score = 0.0
    direction = None
    tags = {}
    s_zone = s_flow = s_crowd = s_gate = 0.0

    atr_val = _f(row.get("atr"))
    px = _f(row.get("close"))
    regime = row.get("regime", "RANGE")
    if atr_val <= 0 or px <= 0:
        return None

    # ── LAYER 1: Market Map (max 30 pts) ─────────────────────
    if regime != "TREND_UP" and row.get("sweep_sup"):
        score += 30; s_zone += 30
        direction = "BUY"; tags["zone"] = "sup_sweep"
    elif regime != "TREND_DOWN" and row.get("sweep_res"):
        score += 30; s_zone += 30
        direction = "SELL"; tags["zone"] = "res_sweep"
    elif regime == "RANGE":
        prior_low = _f(row.get("prior_low"))
        prior_high = _f(row.get("prior_high"))
        rsi_val = _f(row.get("rsi"), 50)
        if prior_low > 0 and (px - prior_low) <= 0.3 * atr_val and rsi_val < 45:
            score += 25; s_zone += 25
            direction = "BUY"; tags["zone"] = "level_bounce"
        elif prior_high > 0 and (prior_high - px) <= 0.3 * atr_val and rsi_val > 55:
            score += 25; s_zone += 25
            direction = "SELL"; tags["zone"] = "level_bounce"
    elif regime == "TREND_UP" and px > _f(row.get("prior_high")):
        score += 25; s_zone += 25
        direction = "BUY"; tags["zone"] = "breakout"
    elif regime == "TREND_DOWN" and px < _f(row.get("prior_low")):
        score += 25; s_zone += 25
        direction = "SELL"; tags["zone"] = "breakout"

    if direction is None:
        return None

    # ── LAYER 2: Flow (max 15 pts) ───────────────────────────
    flow_pts, flow_tags = _flow_score(row, direction)
    score += flow_pts
    s_flow += flow_pts
    tags.update(flow_tags)

    # ── LAYER 3: Crowding (max 43 pts) ───────────────────────
    fund = _f(extra.get("funding"))
    oi_chg = _f(extra.get("oi_chg"))

    if direction == "BUY":
        if fund < -0.0001:
            score += 15; s_crowd += 15
        elif fund > 0.0001:
            score -= 12; s_crowd -= 12
    else:
        if fund > 0.0001:
            score += 15; s_crowd += 15
        elif fund < -0.0001:
            score -= 12; s_crowd -= 12

    if direction == "BUY" and fund < 0 and oi_chg > 0.03:
        score += 5; s_crowd += 5; tags["oi_squeeze"] = True
    if direction == "SELL" and fund > 0 and oi_chg > 0.03:
        score += 5; s_crowd += 5; tags["oi_squeeze"] = True

    div = _f(extra.get("funding_div"))
    div_z = _f(extra.get("funding_div_z"))
    if direction == "SELL" and div > cfg.DIV_THRESH and div_z > cfg.DIV_Z_THRESH:
        score += cfg.DIV_BOOST
        s_crowd += cfg.DIV_BOOST
        tags["div"] = "bn_crowded_long"
    elif direction == "BUY" and div < -cfg.DIV_THRESH and div_z < -cfg.DIV_Z_THRESH:
        score += cfg.DIV_BOOST
        s_crowd += cfg.DIV_BOOST
        tags["div"] = "bn_crowded_short"

    # ── LAYER 4: Regime / Session / Gate ─────────────────────
    hour = extra.get("hour_utc", 12)

    # FIX #4: Counter-trend sweep gets reduced penalty (-10 instead of -25)
    if direction == "BUY" and regime == "TREND_DOWN":
        penalty = -10 if tags.get("zone", "").endswith("sweep") else -25
        score += penalty; s_gate += penalty
    elif direction == "SELL" and regime == "TREND_UP":
        penalty = -10 if tags.get("zone", "").endswith("sweep") else -25
        score += penalty; s_gate += penalty

    # ✅ FIXED: Session bonus only — no penalty (to avoid over-constraining)
    if 8 <= hour <= 16:
        score += 10; s_gate += 10
        tags["session"] = "good"
    else:
        tags["session"] = "off"   # neutral, no penalty

    # High volatility gate
    rv_pct = _f(row.get("rv_pct"), 0.5)
    if rv_pct > 0.9:
        score -= 10; s_gate -= 10
        tags["high_vol"] = True

    # ── Quality-First Gates (safe subset) ────────────────────
    if _f(row.get("vol_ratio"), 0) < cfg.VOL_CONFIRM_RATIO:
        return None
    rv = _f(row.get("rv_pct"), 0.5)
    if rv < cfg.VOL_BAND_LOW or rv > cfg.VOL_BAND_HIGH:
        return None

    # ── Final MIN_SCORE gate ─────────────────────────────────
    if score < cfg.MIN_SCORE:
        return None

    # SL/TP calculation
    if direction == "BUY":
        sl, tp = px - cfg.SL_ATR * atr_val, px + cfg.SL_ATR * atr_val * cfg.TP_RR
    else:
        sl, tp = px + cfg.SL_ATR * atr_val, px - cfg.SL_ATR * atr_val * cfg.TP_RR

    return {
        "side": direction,
        "entry": px,
        "sl": round(sl, 2),
        "tp": round(tp, 2),
        "score": round(score, 1),
        "regime": regime,
        "s_zone": round(s_zone, 1),
        "s_flow": round(s_flow, 1),
        "s_crowd": round(s_crowd, 1),
        "s_gate": round(s_gate, 1),
        "atr_pct": round(atr_val / px * 100, 3),
        **tags,
    }
