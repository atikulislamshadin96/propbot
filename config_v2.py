import os

# ── Basic Settings ──────────────────────────────────────────
SYMBOL = "BTCUSDT"
INTERVAL = "15m"
MIN_SCORE = 70
SL_ATR = 1.5
TP_RR = 2.0
MAX_TRADES_DAY = 3
MAX_POSITIONS = 2
FEE_PCT = 0.05

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
LAYER_2_MAX_POINTS = 15   # was 31 (triple-counted)

# ── Layer 3: GEX (gated) + Divergence ───────────────────────
USE_GEX = False
GEX_BOOST = 8
GEX_WALL_BOOST = 5
GEX_ZERO_PENALTY = 6
GEX_ZERO_DIST_PCT = 1.0
DIV_THRESH = 0.00005
DIV_Z_THRESH = 1.0
DIV_BOOST = 8
