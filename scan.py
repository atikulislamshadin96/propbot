import requests
import requests
import pandas as pd
from datetime import datetime, timezone

import config_v2 as cfg
from binance_data import klines
from bybit_data import bybit_funding_current, bybit_open_interest_history
from datahub import funding_divergence_current
from features import compute_features
from signals_v2 import evaluate
from deribit_skew import skew_features
from hl_funding import get_hl_funding_features
import paper_db as db

INTERVAL = cfg.INTERVAL
_HL_Z_CACHE = {}


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


def get_hyperliquid_data(coin):
    """Non-blocked funding/OI source (works from US runners).
    Hyperliquid pays hourly; x8 to match 8h Binance-equivalent."""
    try:
        r = requests.post("https://api.hyperliquid.xyz/info",
                          json={"type": "metaAndAssetCtxs"}, timeout=10)
        r.raise_for_status()
        meta, ctxs = r.json()
        for i, asset in enumerate(meta["universe"]):
            name = asset.get("name", "")
            if name == coin or name.startswith(coin):
                return float(ctxs[i]["funding"]) * 8.0, float(ctxs[i]["openInterest"])
    except Exception as e:
        print(f"[WARN] hyperliquid failed for {coin}: {e}")
    return 0.0, 0.0


def get_hyperliquid_funding_z(coin, days=7):
    """Return the latest cached 7-day Hyperliquid funding z-score for live parity."""
    if coin in _HL_Z_CACHE:
        return _HL_Z_CACHE[coin]
    try:
        features = get_hl_funding_features(coin, days=days)
        value = float(features["hl_funding_z"].iloc[-1]) if not features.empty else 0.0
    except Exception as exc:
        print(f"[WARN] {coin} Hyperliquid funding z-score unavailable: {exc}")
        value = 0.0
    _HL_Z_CACHE[coin] = value
    return value


def collect_gex():
    try:
        import gex_collector
        snap = gex_collector.snapshot()
        if snap:
            print(f"[GEX] dealer_neg={snap['dealer_gex_neg']} "
                  f"wall={snap['nearest_wall_strike']} ({snap['wall_dist_pct']}%)")
    except Exception as e:
        print(f"[GEX] skip: {e}")


def scan_symbol(sym):
    coin = sym.replace("USDT", "")
    try:
        rows = klines(sym, INTERVAL, 1000)
    except Exception as e:
        print(f"[ERROR] {sym} klines: {e}")
        return
    if not rows or len(rows) < 100:
        return

    df = pd.DataFrame(rows).sort_values("ts").reset_index(drop=True)
    df = compute_features(df)

    # ── Funding: Bybit → fallback Hyperliquid (no silent zero) ──
    try:
        fund = bybit_funding_current(sym)
        if fund == 0.0:
            raise ValueError("zero funding")
    except Exception:
        fund, _ = get_hyperliquid_data(coin)
        print(f"[INFO] {sym} funding via hyperliquid: {fund:+.6f}")

    # ── OI: Bybit → with explicit warning on failure ──
    try:
        oi = bybit_open_interest_history(sym, 9)
        oi_chg = (oi[0]["oi"] - oi[-1]["oi"]) / oi[-1]["oi"] if len(oi) >= 2 else 0.0
    except Exception as e:
        print(f"[WARN] {sym} OI zeroed (US-blocked): {e}")
        oi_chg = 0.0

    # ── Divergence: bybit-okx → with explicit warning on failure ──
    try:
        fdiv, fdivz = funding_divergence_current(sym)
    except Exception as e:
        print(f"[WARN] {sym} divergence zeroed (US-blocked): {e}")
        fdiv, fdivz = 0.0, 0.0

    # ── SL/TP check on last completed candle for this symbol ──
    if len(df) >= 2:
        last = df.iloc[-2]
        for t in db.check_and_close(sym, float(last["high"]), float(last["low"]), cfg.FEE_PCT):
            emoji = "✅" if t["pnl_pct"] > 0 else "❌"
            send_telegram(f"{emoji} *{t.get('symbol', sym)}* closed\n"
                          f"Side: {t['side']} | PnL: {t['pnl_pct']:+.2f}%")
            print(f"[CLOSE] {sym} #{t['id']} {t['status'].upper()} pnl={t['pnl_pct']:+.2f}%")

    # ── Global + per-symbol risk gates ──
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

    # ── Fetch Deribit skew features (cached per currency within run) ──
    skew = skew_features(coin)
    hl_funding_z = get_hyperliquid_funding_z(coin)

    # ── Evaluate signal on last completed candle ──
    row = df.iloc[-2].to_dict()
    extra = {"funding": fund, "oi_chg": oi_chg, "funding_div": fdiv,
             "funding_div_z": fdivz, "hl_funding_z": hl_funding_z,
             "hour_utc": datetime.now(timezone.utc).hour,
             "dvol": skew.get("dvol"), "dvol_pct": skew.get("dvol_pct"),
             "rr_25d": skew.get("rr_25d")}
    
    # 🔑 RECOVERY FIX: Pass is_backtest=False for live scanning
    # This ensures MIN_SCORE_LIVE (40) and hard Option A reject are used
    sig = evaluate(row, extra, is_backtest=False)

    if sig is None:
        dvol_pct = skew.get("dvol_pct")
        rr = skew.get("rr_25d")
        print(f"[IDLE] {sym} no signal | score < {cfg.MIN_SCORE_LIVE} | "
              f"fund={fund:+.6f} div={fdiv:+.6f} "
              f"hl_z={hl_funding_z:+.2f} "
              f"dvol_pct={dvol_pct if dvol_pct is not None else '—'} "
              f"rr_25d={rr if rr is not None else '—'}")
        return

    # ── Open paper trade + log + notify ──
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
    collect_gex()
    for sym in cfg.SYMBOLS:
        scan_symbol(sym)


if __name__ == "__main__":
    main()
