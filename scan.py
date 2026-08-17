import requests
import pandas as pd
from datetime import datetime, timezone

import config_v2 as cfg
from binance_data import klines
from bybit_data import bybit_funding_current, bybit_open_interest_history
from datahub import funding_divergence_current
from features import compute_features
from signals_v2 import evaluate
import paper_db as db

INTERVAL = cfg.INTERVAL


def send_telegram(msg):
    if not (cfg.TG_TOKEN and cfg.TG_CHAT_ID):
        return
    try:
        requests.post(f"https://api.telegram.org/bot{cfg.TG_TOKEN}/sendMessage",
                      json={"chat_id": cfg.TG_CHAT_ID, "text": msg[:4000],
                            "parse_mode": "Markdown"}, timeout=10)
    except Exception:
        pass


def heartbeat():
    try:
        with open("keepalive.txt", "w") as f:
            f.write(f"last_scan: {datetime.now(timezone.utc).isoformat()}\n")
    except Exception:
        pass


def scan_symbol(sym):
    try:
        rows = klines(sym, INTERVAL, 1000)
    except Exception as e:
        print(f"[ERROR] {sym} klines: {e}")
        return
    if not rows or len(rows) < 100:
        return

    df = pd.DataFrame(rows).sort_values("ts").reset_index(drop=True)
    df = compute_features(df)

    try:
        fund = bybit_funding_current(sym)
    except Exception:
        fund = 0.0
    try:
        oi = bybit_open_interest_history(sym, 9)
        oi_chg = (oi[0]["oi"] - oi[-1]["oi"]) / oi[-1]["oi"] if len(oi) >= 2 else 0.0
    except Exception:
        oi_chg = 0.0
    try:
        fdiv, fdivz = funding_divergence_current(sym)
    except Exception:
        fdiv, fdivz = 0.0, 0.0

    # SL/TP for this symbol
    if len(df) >= 2:
        last = df.iloc[-2]
        for t in db.check_and_close(sym, float(last["high"]), float(last["low"]), cfg.FEE_PCT):
            emoji = "✅" if t["pnl_pct"] > 0 else "❌"
            send_telegram(f"{emoji} *{t.get('symbol', sym)}* closed\n"
                          f"Side: {t['side']} | PnL: {t['pnl_pct']:+.2f}%")
            print(f"[CLOSE] {sym} #{t['id']} {t['status'].upper()} pnl={t['pnl_pct']:+.2f}%")

    # Global + per-symbol gates
    if len(db.open_trades()) >= cfg.MAX_POSITIONS:
        print(f"[SKIP] {sym} max total positions")
        return
    if len(db.open_trades(sym)) >= 1:
        print(f"[SKIP] {sym} already open")
        return
    daily_pnl = db.daily_pnl_pct()
    if daily_pnl < 0 and abs(daily_pnl) >= cfg.P["daily_loss_pct"] * 0.8:
        print(f"[SKIP] {sym} daily circuit breaker")
        return
    if not db.check_cooldown(30):
        print(f"[SKIP] {sym} cooldown")
        return

    row = df.iloc[-2].to_dict()
    extra = {"funding": fund, "oi_chg": oi_chg, "funding_div": fdiv,
             "funding_div_z": fdivz, "hour_utc": datetime.now(timezone.utc).hour}
    sig = evaluate(row, extra)

    if sig is None:
        print(f"[IDLE] {sym} no signal | score < {cfg.MIN_SCORE}")
        return

    sig["symbol"] = sym
    db.log_signal(sig)
    tid = db.open_trade(sig, cfg.MAX_RISK_PCT)
    send_telegram(f"🎯 *NEW SIGNAL* {sig['side']} {sym}\n"
                  f"Score: {sig['score']} | Regime: {sig['regime']}\n"
                  f"Entry: ${sig['entry']:.2f} | SL: ${sig['sl']:.2f} | TP: ${sig['tp']:.2f}")
    print(f"[SIGNAL] {sym} #{tid} {sig['side']} @ {sig['entry']:.2f} "
          f"score={sig['score']} zone={sig.get('zone', '—')}")


def main():
    print(f"[{datetime.now(timezone.utc).isoformat()}] scan start | "
          f"{cfg.SYMBOLS} | program={cfg.ACTIVE_PROGRAM}")
    heartbeat()
    for sym in cfg.SYMBOLS:
        scan_symbol(sym)


if __name__ == "__main__":
    main()
