# ============================================================
# backtest_v2.py — Multi-asset, non-blocked data sources
# + Phase 1: Deribit DVOL/skew regime gate
# + Recovery: Passes is_backtest=True to evaluate()
# python backtest_v2.py --days 90 --with-foi
# ============================================================
import argparse
import requests
import numpy as np
import pandas as pd
from datetime import datetime, timezone

import config_v2 as cfg
from bybit_data import bybit_funding_history, bybit_open_interest_history
from datahub import funding_divergence_series
from features import compute_features
from signals_v2 import evaluate
from deribit_skew import get_dvol_series


def fetch_range(symbol, interval, days):
    """Paginated klines — non-blocked vision endpoint"""
    BASE = "https://data-api.binance.vision"
    out = []
    end = int(datetime.now(timezone.utc).timestamp() * 1000)
    start = end - days * 86400 * 1000
    cursor = start
    while cursor < end:
        r = requests.get(f"{BASE}/api/v3/klines",
                         params={"symbol": symbol, "interval": interval,
                                 "limit": 1000, "startTime": cursor, "endTime": end},
                         timeout=20)
        r.raise_for_status()
        batch = r.json()
        if not batch:
            break
        out.extend(batch)
        nxt = int(batch[-1][0]) + 1
        if nxt <= cursor:
            break
        cursor = nxt
    rows = [{"ts": int(k[0]), "open": float(k[1]), "high": float(k[2]),
             "low": float(k[3]), "close": float(k[4]), "volume": float(k[5]),
             "taker_buy": float(k[9])} for k in out]
    return (pd.DataFrame(rows).drop_duplicates("ts")
            .sort_values("ts").reset_index(drop=True))


def merge_foi(df, symbol):
    """Funding/OI/divergence from non-blocked sources"""
    df = df.copy()
    df["time"] = pd.to_datetime(df["ts"], unit="ms", utc=True)
    try:
        fh = pd.DataFrame(bybit_funding_history(symbol, 200))
        fh["time"] = pd.to_datetime(fh["ts"], unit="ms", utc=True)
        df = pd.merge_asof(df, fh[["time", "rate"]].rename(
            columns={"rate": "funding"}).sort_values("time"),
            on="time", direction="backward")
    except Exception:
        df["funding"] = 0.0
    try:
        oh = pd.DataFrame(bybit_open_interest_history(symbol, 200))
        oh["time"] = pd.to_datetime(oh["ts"], unit="ms", utc=True)
        df = pd.merge_asof(df, oh[["time", "oi"]].sort_values("time"),
                           on="time", direction="backward")
        df["oi_chg"] = df["oi"].pct_change(32)
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


def merge_skew(df, currency):
    """Merge Deribit DVOL + trailing percentile onto df by time (backward asof).
    RR has no public history — left as NaN (gate simply won't fire on it)."""
    df = df.copy()
    df["time"] = pd.to_datetime(df["ts"], unit="ms", utc=True)
    try:
        s = get_dvol_series(currency, days=90)
        if len(s) >= 2:
            s_pct = s.rolling(24 * 90, min_periods=24 * 7).rank(pct=True)
            sdf = pd.DataFrame({"time": s.index, "dvol": s.values,
                                "dvol_pct": s_pct.values}).dropna()
            df = pd.merge_asof(df, sdf.sort_values("time"),
                               on="time", direction="backward")
    except Exception as e:
        print(f"[WARN] deribit skew history failed for {currency}: {e}")
    df["dvol"] = df.get("dvol", pd.Series(np.nan, index=df.index)).fillna(np.nan)
    df["dvol_pct"] = df.get("dvol_pct", pd.Series(np.nan, index=df.index)).fillna(0.5)
    df["rr_25d"] = np.nan
    return df


def run(symbols, days, with_foi):
    if isinstance(symbols, str):
        symbols = [symbols]
    all_trades = []
    n_bars = 0
    for sym in symbols:
        df = fetch_range(sym, "15m", days)
        if with_foi:
            df = merge_foi(df, sym)
            df = merge_skew(df, sym.replace("USDT", ""))
        else:
            df["funding"] = 0.0
            df["oi_chg"] = 0.0
            df["div"] = 0.0
            df["div_z"] = 0.0
            df["dvol"] = np.nan
            df["dvol_pct"] = 0.5
            df["rr_25d"] = np.nan
        df = compute_features(df)
        n_bars = max(n_bars, len(df))

        trades, open_pos = [], None
        fee = cfg.FEE_PCT
        n = len(df)
        for i in range(60, n):
            c = df.iloc[i]
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
                    trades.append({**o, "symbol": sym, "exit": exit_px, "res": res,
                                   "pnl_pct": round(pnl - fee, 3), "close_bar": i})
                    open_pos = None

            if open_pos is None and i + 1 < n:
                row = df.iloc[i].to_dict()
                extra = {"funding": row.get("funding", 0.0),
                         "oi_chg": row.get("oi_chg", 0.0),
                         "funding_div": row.get("div", 0.0),
                         "funding_div_z": row.get("div_z", 0.0),
                         "hour_utc": pd.Timestamp(row["ts"], unit="ms", tz="UTC").hour,
                         "dvol": row.get("dvol"),
                         "dvol_pct": row.get("dvol_pct", 0.5),
                         "rr_25d": row.get("rr_25d")}
                
                # 🔑 RECOVERY FIX: Pass is_backtest=True so signals_v2 uses MIN_SCORE_BACKTEST (25)
                # and applies soft penalty for Option A instead of hard reject.
                sig = evaluate(row, extra, is_backtest=True)
                
                if sig:
                    nxt = df.iloc[i + 1]
                    open_pos = {"side": sig["side"], "entry": float(nxt["open"]),
                                "sl": sig["sl"], "tp": sig["tp"],
                                "regime": sig["regime"], "zone": sig.get("zone", ""),
                                "open_bar": i + 1}
        all_trades += trades
    return {"trades": all_trades, "n_bars": n_bars, "df": None}


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
        peak = np.maximum.accumulate(eq)
        dd = (eq - peak) / peak
        if dd.min() < -0.10:  # trailing drawdown
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
    ap.add_argument("--days", type=int, default=90)
    ap.add_argument("--with-foi", action="store_true")
    a = ap.parse_args()

    res = run(cfg.SYMBOLS, a.days, a.with_foi)
    m = metrics(res["trades"])
    mc = monte_carlo(res["trades"])
    co = cohort(res["trades"])

    print("=== BACKTEST", cfg.SYMBOLS, a.days, "days ===")
    for k, v in m.items():
        print(f"  {k}: {v}")
    print("=== MONTE CARLO ===")
    for k, v in mc.items():
        print(f"  {k}: {v}")
    print("=== COHORT (by zone) ===")
    for z, v in co.items():
        print(f"  {z}: n={v['n']} wr={v['wr']}%")
