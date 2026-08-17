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

SL_ATR = 1.5
TP_RR = 2.0
MAX_TRADES_DAY = 3
MAX_POSITIONS = 2
FEE_PCT = 0.05

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
        "max_risk_pct": 1.5, "max_positions": 2,
    },
    "2step_pro": {
        "daily_loss_pct": 3.0, "total_dd_pct": 6.0,
        "max_risk_pct": 1.0, "max_positions": 2,
    },
}
ACTIVE_PROGRAM = "2step_standard"
P = PROGRAMS[ACTIVE_PROGRAM]
DAILY_LOSS_PCT = P["daily_loss_pct"]
TOTAL_DD_PCT = P["total_dd_pct"]
MAX_RISK_PCT = P["max_risk_pct"]

# ── Layer 2 (Fixed — single composite flow score) ───────────
LAYER_2_MAX_POINTS = 15

# ── Layer 3: GEX (gated) + Divergence ───────────────────────
USE_GEX = False
GEX_BOOST = 8
GEX_WALL_BOOST = 5
GEX_ZERO_PENALTY = 6
GEX_ZERO_DIST_PCT = 1.0
DIV_THRESH = 0.00005
DIV_Z_THRESH = 1.0
DIV_BOOST = 8

# ── Quality-First Gates (safe subset) ────────────────────────
VOL_CONFIRM_RATIO = 0.8
VOL_BAND_LOW = 0.10
VOL_BAND_HIGH = 1.0
