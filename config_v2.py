import os

# ── Basic Settings ──────────────────────────────────────────
SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
SYMBOL = SYMBOLS[0]   # backward compatibility
INTERVAL = "15m"

# ── Adaptive MIN_SCORE (Live vs Backtest) ───────────────────
# Backtest-এ L2/L3 data US-blocked → zeroed, তাই score কমে যায়
# Live-তে সব data available → full 40 threshold
MIN_SCORE_LIVE = 40
MIN_SCORE_BACKTEST = 25
MIN_SCORE = MIN_SCORE_LIVE  # backward compatibility alias

# ── Risk Parameters (🔑 Patch C: MAX_RISK_PCT now caps SL) ──
SL_ATR = 1.5
TP_RR = 2.0
MAX_TRADES_DAY = 3
MAX_POSITIONS = 2
FEE_PCT = 0.05
MAX_RISK_PCT = 0.50   # Reduced per Genspark recommendation (was 1.5)

# ── Option A Soft Gate (Recovery from earlier mistake) ──────
# Live: s_flow < 5 → hard reject (data available)
# Backtest: s_flow < 5 → soft penalty -10 (data often zeroed due to US-block)
OPTION_A_SOFT = True
L2_ZERO_SOFTEN = True

# ── Secrets (GitHub Secrets থেকে) ───────────────────────────
NEWS_API_KEY = os.getenv("NEWS_API_KEY", "")
TG_TOKEN = os.getenv("TG_TOKEN", "")
TG_CHAT_ID = os.getenv("TG_CHAT_ID", "")

# ── Program Presets (Track 0: Exposure Caps) ────────────────
PROGRAMS = {
    "2step_standard": {
        "daily_loss_pct": 5.0, "total_dd_pct": 10.0,
        "max_risk_pct": 0.50, "max_positions": 2,   # ← Updated to 0.50
    },
    "2step_pro": {
        "daily_loss_pct": 3.0, "total_dd_pct": 6.0,
        "max_risk_pct": 0.35, "max_positions": 2,   # ← Updated (was 1.0)
    },
}
ACTIVE_PROGRAM = "2step_standard"
P = PROGRAMS[ACTIVE_PROGRAM]
DAILY_LOSS_PCT = P["daily_loss_pct"]
TOTAL_DD_PCT = P["total_dd_pct"]
# 🔑 MAX_RISK_PCT is now explicit at top level (Patch C)
# P["max_risk_pct"] still available for program-specific override if needed

# ── Layer 2 (Fixed — single composite flow score) ───────────
LAYER_2_MAX_POINTS = 15

# ── Layer 3: GEX (gated) + Divergence + HL Funding ─────────
USE_GEX = False
GEX_BOOST = 8
GEX_WALL_BOOST = 5
GEX_ZERO_PENALTY = 6
GEX_ZERO_DIST_PCT = 1.0
DIV_THRESH = 0.00005
DIV_Z_THRESH = 1.0
DIV_BOOST = 8

# Hyperliquid funding z-score threshold (L3 Revival)
HL_FUNDING_Z_THRESH = 2.0   # |z| >= 2.0 = crowded extreme

# ── Funding-Divergence Research (paper candidates only) ───────
FUNDING_ACTIVE_COIN = "BTC"
FUNDING_HISTORY_DAYS = 90
FUNDING_Z_WINDOW_HOURS = 168
FUNDING_MIN_HISTORY_HOURS = 72
FUNDING_Z_ENTRY = 2.5
FUNDING_EXPECTED_HOLD_HOURS = 8
FUNDING_ROUNDTRIP_COST_BPS = 30.0
FUNDING_COST_BUFFER = 1.25

# ── Quality-First Gates (safe subset) ────────────────────────
VOL_CONFIRM_RATIO = 0.8
VOL_BAND_LOW = 0.10
VOL_BAND_HIGH = 1.0
