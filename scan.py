# ============================================================
# scan.py — Main orchestrator, runs every 15 min via cron
# ============================================================
import os
import requests
import pandas as pd
from datetime import datetime, timezone

import config_v2 as cfg
from binance_data import klines, funding_current, open_interest
from datahub import funding_divergence_current
from features import compute_features
from signals_v2 import evaluate
import paper_db as db

SYMBOL = cfg.SYMBOL
INTERVAL = cfg.INTERVAL


def send_telegram(msg):
    """Send message to Telegram (silent failure if not configured)"""
    if not (cfg.TG_TOKEN and cfg.TG_CHAT_ID):
        return
    try:
        url = f"https://api.telegram.org/bot{cfg.TG_TOKEN}/sendMessage"
        payload = {"chat_id": cfg.TG_CHAT_ID, "text": msg[:4000],
                   "parse_mode": "Markdown"}
        requests.post(url, json=payload, timeout=10)
    except Exception:
        pass


def heartbeat():
    """Update keepalive.txt so GitHub doesn't disable the cron"""
    try:
        with open("keepalive.txt", "w") as f:
            f.write(f"last_scan: {datetime.now(timezone.utc).isoformat()}\n")
    except Exception:
        pass


def main():
    print(f"[{datetime.now(timezone.utc).isoformat()}] scan start | {SYMBOL} {INTERVAL}")
    heartbeat()

    # ── 1. Fetch data ────────────────────────────────────────
    try:
        rows = klines(SYMBOL, INTERVAL, 500)
    except Exception as e:
        print(f"[ERROR] klines failed: {e}")
        return
    df = pd.DataFrame(rows).sort_values("ts").reset_index(drop=True)
    df = compute_features(df)

    # ── 2. Funding + OI + divergence ─────────────────────────
    try:
        fund = funding_current(SYMBOL)
    except Exception:
        fund = 0.0
    try:
        oi_now = open_interest(SYMBOL)
    except Exception:
        oi_now = 0.0
    # 24-bar OI change (approx)
    oi_chg = 0.0  # placeholder — live OI snapshot only for now
    try:
        fdiv, fdivz = funding_divergence_current(SYMBOL)
    except Exception:
        fdiv, fdivz = 0.0, 0.0

    # ── 3. Check SL/TP on last completed candle ──────────────
    if len(df) >= 2:
        last_done = df.iloc[-2]
        closed = db.check_and_close(
            float(last_done["high"]),
            float(last_done["low"]),
            fee_pct=cfg.FEE_PCT,
        )
        for t in closed:
            emoji = "✅" if t["pnl_pct"] > 0 else "❌"
            msg = (f"{emoji} *{SYMBOL}* trade closed\n"
                   f"Side: {t['side']} | PnL: {t['pnl_pct']:+.2f}%\n"
                   f"Entry: {t['entry']} → Exit: {t['exit']} ({t['status']})")
            send_telegram(msg)
            print(f"[CLOSE] #{t['id']} {t['status'].upper()} "
                  f"pnl={t['pnl_pct']:+.2f}%")

    # ── 4. Pre-signal gates ──────────────────────────────────
    # Gate A: MAX_POSITIONS
    if len(db.open_trades()) >= cfg.MAX_POSITIONS:
        print(f"[SKIP] max open positions ({cfg.MAX_POSITIONS}) reached")
        return

    # Gate B: Daily loss circuit breaker (Track 0)
    daily_pnl = db.daily_pnl_pct()
    daily_limit = cfg.P["daily_loss_pct"]
    if daily_pnl < 0 and abs(daily_pnl) >= daily_limit * 0.8:
        print(f"[SKIP] daily loss {daily_pnl:+.2f}% near limit "
              f"({daily_limit}%) — circuit breaker")
        return

    # Gate C: 30-min cooldown after last trade
    if not db.check_cooldown(30):
        print("[SKIP] 30-min cooldown active")
        return

    # ── 5. Generate signal on last completed candle ──────────
    row = df.iloc[-2].to_dict()
    extra = {
        "funding": fund,
        "oi_chg": oi_chg,
        "funding_div": fdiv,
        "funding_div_z": fdivz,
        "hour_utc": datetime.now(timezone.utc).hour,
    }
    sig = evaluate(row, extra)

    if sig is None:
        print(f"[IDLE] no signal | score < {cfg.MIN_SCORE} | "
              f"fund={fund:+.5f} div={fdiv:+.5f}")
        return

    # ── 6. Open trade + log + notify ─────────────────────────
    db.log_signal(sig)
    trade_id = db.open_trade(sig, cfg.MAX_RISK_PCT)

    msg = (f"🎯 *NEW SIGNAL* {sig['side']} {SYMBOL}\n"
           f"Score: {sig['score']} | Regime: {sig['regime']}\n"
           f"Entry: ${sig['entry']:.2f}\n"
           f"SL: ${sig['sl']:.2f} | TP: ${sig['tp']:.2f}\n"
           f"Zone: {sig.get('zone','—')} | Div: {sig.get('div','—')}")
    send_telegram(msg)

    print(f"[SIGNAL] #{trade_id} {sig['side']} @ {sig['entry']:.2f} "
          f"score={sig['score']} | {sig['regime']} | "
          f"zone={sig.get('zone','—')}")


if __name__ == "__main__":
    main()
