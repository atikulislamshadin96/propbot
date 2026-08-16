# ============================================================
# gex_collector.py — Deribit GEX snapshot (Track 3, gated)
# USE_GEX=False until 4-week validation passes.
# ============================================================
import json, os, math
from datetime import datetime, timezone
from deribit_data import get_book_summary, get_ticker

DATA = "data/gex"

def parse_instrument(name):
    _, exp, strike, cp = name.split("-")
    return (datetime.strptime(exp, "%d%b%y").replace(tzinfo=timezone.utc),
            float(strike), cp)

def bs_gamma(S, K, T, sigma):
    if T <= 0 or sigma <= 0:
        return 0.0
    d1 = (math.log(S / K) + 0.5 * sigma * sigma * T) / (sigma * math.sqrt(T))
    phi = math.exp(-0.5 * d1 * d1) / math.sqrt(2 * math.pi)
    return phi / (S * sigma * math.sqrt(T))

def snapshot():
    try:
        instruments = get_book_summary("BTC")
        spot = float(get_ticker("BTC-PERPETUAL").get("index_price", 0))
        if not spot or not instruments:
            return None
    except Exception:
        return None

    rows = []
    now = datetime.now(timezone.utc)
    for it in instruments:
        name = it.get("instrument_name", "")
        oi = float(it.get("open_interest", 0) or 0)
        iv = it.get("mark_iv")
        if "BTC-" not in name or oi <= 0 or not iv or iv <= 0:
            continue
        try:
            exp, strike, _ = parse_instrument(name)
        except Exception:
            continue
        T = (exp - now).total_seconds() / (365 * 86400)
        if T <= 0:
            continue
        g = bs_gamma(spot, strike, T, iv / 100.0)
        rows.append({"strike": strike, "oi": oi,
                     "gex_usd_1pct": g * spot * spot * 0.01 * oi})

    if not rows:
        return None
    rows.sort(key=lambda r: r["strike"])
    net = sum(r["gex_usd_1pct"] for r in rows)
    dealer_gex = -net  # equity convention (unverified for crypto)

    zero_flip = None
    for a, b in zip(rows, rows[1:]):
        if (a["gex_usd_1pct"] >= 0) != (b["gex_usd_1pct"] >= 0):
            zero_flip = (a["strike"] + b["strike"]) / 2
            break
    wall = max(rows, key=lambda r: abs(r["gex_usd_1pct"]))

    snap = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "spot": round(spot, 1),
        "n_instruments": len(rows),
        "net_market_gex_usd_1pct": round(net, 0),
        "dealer_gex_neg": dealer_gex < 0,
        "zero_gamma_flip": zero_flip,
        "nearest_wall_strike": wall["strike"],
        "wall_dist_pct": round(abs(wall["strike"] - spot) / spot * 100, 2),
        "wall_above": wall["strike"] > spot,
    }
    os.makedirs(DATA, exist_ok=True)
    with open(f"{DATA}/gex.jsonl", "a") as f:
        f.write(json.dumps(snap) + "\n")
    return snap

if __name__ == "__main__":
    s = snapshot()
    if s:
        print(f"[GEX] dealer_neg={s['dealer_gex_neg']} "
              f"wall={s['nearest_wall_strike']} ({s['wall_dist_pct']}%)")
