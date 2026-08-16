# ============================================================
# signals_v2.py — 4-layer confluence signal engine
#   Layer 1: Market Map (max 30)
#   Layer 2: Flow (max 15, FIXED — single composite)
#   Layer 3: Crowding (max 43)
#   Layer 4: Regime/Session/Gate (max 25)
# ============================================================
import config_v2 as cfg
from utils import _f


def _flow_score(row, direction):
    """Layer 2 FIXED — single composite score (max 15 points)
    Replaces the old triple-counted CVD/VPIN/taker (31 points).
    VPIN-proxy dropped: mislabeled noise (same data as CVD).
    """
    flow_points = 0.0
    tags = {}

    # ── CVD Divergence (0-10 points) ─────────────────────────
    # Bullish: price new low + CVD higher low (exhaustion)
    # Bearish: price new high + CVD lower high (exhaustion)
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
    """Generate signal score. Returns dict or None if below MIN_SCORE.
    extra = {funding, oi_chg, funding_div, funding_div_z, hour_utc}
    """
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
            score += 15; s_zone += 15
            direction = "BUY"; tags["zone"] = "level_bounce"
        elif prior_high > 0 and (prior_high - px) <= 0.3 * atr_val and rsi_val > 55:
            score += 15; s_zone += 15
            direction = "SELL"; tags["zone"] = "level_bounce"
    elif regime == "TREND_UP" and px > _f(row.get("prior_high")):
        score += 20; s_zone += 20
        direction = "BUY"; tags["zone"] = "breakout"
    elif regime == "TREND_DOWN" and px < _f(row.get("prior_low")):
        score += 20; s_zone += 20
        direction = "SELL"; tags["zone"] = "breakout"

    if direction is None:
        return None

    # ── LAYER 2: Flow (max 15 pts, FIXED) ────────────────────
    flow_pts, flow_tags = _flow_score(row, direction)
    score += flow_pts
    s_flow += flow_pts
    tags.update(flow_tags)

    # ── LAYER 3: Crowding (max 43 pts) ───────────────────────
    fund = _f(extra.get("funding"))
    oi_chg = _f(extra.get("oi_chg"))

    # Funding rate crowding
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

    # OI + funding squeeze confirmation
    if direction == "BUY" and fund < 0 and oi_chg > 0.03:
        score += 5; s_crowd += 5; tags["oi_squeeze"] = True
    if direction == "SELL" and fund > 0 and oi_chg > 0.03:
        score += 5; s_crowd += 5; tags["oi_squeeze"] = True

    # Multi-exchange funding divergence (Track 4)
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

    # ── LAYER 4: Regime/Session/Gate ─────────────────────────
    hour = extra.get("hour_utc", 12)

    # FIX #4: Layer 1 sweep counter-trend gets reduced penalty (-10)
    # Other mismatches get full -25 penalty
    if direction == "BUY" and regime == "TREND_DOWN":
        penalty = -10 if tags.get("zone", "").endswith("sweep") else -25
        score += penalty; s_gate += penalty
    elif direction == "SELL" and regime == "TREND_UP":
        penalty = -10 if tags.get("zone", "").endswith("sweep") else -25
        score += penalty; s_gate += penalty

    # Session filter
    if 8 <= hour <= 16:
        score += 10; s_gate += 10
        tags["session"] = "good"
    else:
        score -= 10; s_gate -= 10
        tags["session"] = "bad"

    # High volatility gate
    rv_pct = _f(row.get("rv_pct"), 0.5)
    if rv_pct > 0.9:
        score -= 10; s_gate -= 10
        tags["high_vol"] = True

    # ── Final gate ───────────────────────────────────────────
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
