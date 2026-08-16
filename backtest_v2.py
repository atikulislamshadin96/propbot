# ============================================================
# backtest_v2.py — Historical backtest with SAME evaluate() as live
# python backtest_v2.py --days 60 [--with-foi]
# ============================================================
import argparse, requests
import numpy as np
import pandas as pd
from datetime import datetime, timezone

import config_v2 as cfg
from binance_data import funding_history
from bybit_data import bybit_funding_history
from okx_data import okx_funding_history
from datahub import funding_divergence_series
from features import compute_features
from signals_v2 import evaluate

def fetch_range(symbol, interval, days):
    """Paginated klines fetch (Binance max 1000/call)"""
    out = []
    end = int(datetime.now(timezone.utc).timestamp() * 1000)
    start = end - days * 86400 * 1000
    while end > start:
        r = requests.get("https://fapi.binance.com/fapi/v1/klines",
                         params={"symbol": symbol, "interval": interval,
                                 "limit": 1000, "endTime": end}, timeout=20)
        r.raise_for_status()
        batch = r.json()
        if not batch:
            break
        out = batch + out
        end = batch[0][0] - 1
    rows = [{"ts": int(k[0]), "open": float(k[1]), "high": float(k[2]),
             "low": float(k[3]), "close": float(k[4]), "volume": float(k[5]),
             "taker_buy": float(k[9])} for k in out]
    return pd.DataFrame(rows).sort_values("ts").reset_index(drop=True)

def oi_history(symbol, limit=500):
    r = requests.get("https://fapi.binance.com/futures/data/openInterestHist",
                     params={"symbol": symbol, "period": "1h", "limit": limit},
                     timeout=15)
    r.raise_for_status()
    return [{"ts": int(x["timestamp"]), "oi": float(x["sumOpenInterest"])}
            for x in r.json()]

def merge_foi(df, symbol):
    df = df.copy()
    df["time"] = pd.to_datetime(df["ts"], unit="ms", utc=True)
    try:
        fh = pd.DataFrame(funding_history(symbol, 1000))
        fh["time"] = pd.to_datetime(fh["ts"], unit="ms", utc=True)
        df = pd.merge_asof(df, fh[["time", "rate"]].rename(
            columns={"rate": "funding"}).sort_values("time"),
            on="time", direction="backward")
    except Exception:
        df["funding"] = 0.0
    try:
        oh = pd.DataFrame(oi_history(symbol))
        oh["time"] = pd.to_datetime(oh["ts"], unit="ms", utc=True)
        df = pd.merge_asof(df, oh[["time", "oi"]].sort_values("time"),
                           on="time", direction="backward")
        df["oi_chg"] = df["oi"].pct_change(32)  # ~8h on 15m
    except Exception:
        df["oi_chg"] = 0.0
    try:
        ds = funding_divergence_series(symbol)
        if ds is not None:
            ds2 = ds.reset_index().rename(columns={"dt": "time"})
            df = pd.merge_asof(df, ds2[["time", "div", "div_z"]].sort_values("time"),
                               on="time", direction="backward")
    except Exception:
        pass
    df["funding"] = df["funding"].fillna(0.0)
    df["oi_chg"] = df["oi_chg"].fillna(0.0)
    df["div"] = df.get("div", pd.Series(0.0, index=df.index)).fillna(0.0)
    df["div_z"] = df.get("div_z", pd.Series(0.0, index=df.index)).fillna(0.0)
    return df

def run(symbol, days, with_foi):
    df = fetch_range(symbol, "15m", days)
    if with_foi:
        df = merge_foi(df, symbol)
    else:
        df["funding"] = 0.0
        df["oi_chg"] = 0.0
        df["div"] = 0.0
        df["div_z"] = 0.0
    df = compute_features(df)

    trades, open_pos = [], None
    fee = cfg.FEE_PCT
    n = len(df)

    for i in range(60, n):
        c = df.iloc[i]
        # resolve open position on this candle
        if open_pos:
            o = open_pos
            if o["side"] == "BUY":
                if c["low"] <= o["sl"]:   exit_px, res = o["sl"], "sl"
                elif c["high"] >= o["tp"]: exit_px, res = o["tp"], "tp"
                else: exit_px = None
            else:
                if c["high"] >= o["sl"]:  exit_px, res = o["sl"], "sl"
                elif c["low"] <= o["tp"]: exit_px, res = o["tp"], "tp"
                else: exit_px = None
            if exit_px is not None:
                pnl = ((exit_px - o["entry"]) / o["entry"] * 100
                       if o["side"] == "BUY"
                       else (o["entry"] - exit_px) / o["entry"] * 100)
                trades.append({**o, "exit": exit_px, "res": res,
                               "pnl_pct": round(pnl - fee, 3),
                               "close_bar": i})
                open_pos = None

        # new signal on completed candle i, enter at i+1
        if open_pos is None and i + 1 < n:
            row = df.iloc[i].to_dict()
            extra = {"funding": row.get("funding", 0.0),
                     "oi_chg": row.get("oi_chg", 0.0),
                     "funding_div": row.get("div", 0.0),
                     "funding_div_z": row.get("div_z", 0.0),
                     "hour_utc": pd.Timestamp(row["ts"], unit="ms", tz="UTC").hour}
            sig = evaluate(row, extra)
            if sig:
                nxt = df.iloc[i + 1]
                open_pos = {"side": sig["side"], "entry": float(nxt["open"]),
                            "sl": sig["sl"], "tp": sig["tp"],
                            "regime": sig["regime"], "zone": sig.get("zone", ""),
                            "open_bar": i + 1}

    return {"trades": trades, "n_bars": n, "df": df}

def metrics(trades):
    if not trades:
        return {"trades": 0}
    pnls = np.array([t["pnl_pct"] for t in trades])
    wins = pnls[pnls > 0]
    losses = pnls[pnls <= 0]
    gross_w = wins.sum()
    gross_l = abs(losses.sum())
    eq = np.cumprod(1 + pnls / 100)
    peak = np.maximum.accumulate(eq)
    max_dd = float(((eq - peak) / peak).min() * 100)
    return {
        "trades": len(pnls),
        "win_rate": round(100 * len(wins) / len(pnls), 1),
        "expectancy": round(float(pnls.mean()), 3),
        "net_pct": round(float(pnls.sum()), 2),
        "profit_factor": round(gross_w / gross_l, 2) if gross_l > 0 else float("inf"),
        "max_dd_pct": round(max_dd, 2),
    }

def monte_carlo(trades, sims=200):
    if len(trades) < 5:
        return {}
    pnls = np.array([t["pnl_pct"] for t in trades])
    finals, ruins = [], 0
    for _ in range(sims):
        np.random.shuffle(pnls)
        eq = np.cumprod(1 + pnls / 100)
        finals.append(eq[-1])
        if (1 - eq).max() > 0.10:
            ruins += 1
    return {"mc_median_final": round(float(np.median(finals)), 3),
            "mc_ruin_prob": round(100 * ruins / sims, 1)}

def cohort(trades):
    out = {}
    for t in trades:
        z = t.get("zone", "other")
        out.setdefault(z, []).append(t["pnl_pct"])
    return {z: {"n": len(v), "wr": round(100 * sum(1 for x in v if x > 0) / len(v), 1)}
            for z, v in out.items()}

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=60)
    ap.add_argument("--with-foi", action="store_true")
    a = ap.parse_args()

    res = run(cfg.SYMBOL, a.days, a.with_foi)
    m = metrics(res["trades"])
    mc = monte_carlo(res["trades"])
    co = cohort(res["trades"])

    print("=== BACKTEST", cfg.SYMBOL, a.days, "days ===")
    for k, v in m.items():
        print(f"  {k}: {v}")
    print("=== MONTE CARLO ===")
    for k, v in mc.items():
        print(f"  {k}: {v}")
    print("=== COHORT (by zone) ===")
    for z, v in co.items():
        print(f"  {z}: n={v['n']} wr={v['wr']}%")
