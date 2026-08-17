# ============================================================
# deribit_skew.py — Deribit DVOL + 25-delta risk reversal
# Phase 1 advanced layer (vol/skew regime filter)
# US-accessible public REST only. Safe fallback on every path.
# ============================================================
import time
import requests
import numpy as np
import pandas as pd
from datetime import datetime, timezone

BASE = "https://www.deribit.com/api/v2"
TIMEOUT = 15
DVOL_DAYS = 90
DVOL_RESOLUTION = 3600          # hourly DVOL
RR_DELTA_TARGET = 0.25          # 25-delta risk reversal
MAX_TICKER_CALLS = 20           # cap per currency (nearest strikes to spot)
TICKER_SLEEP = 0.25             # ~4 req/s — well under Deribit public limit

# Module-level cache — one Deribit fetch per currency per scan run
_CACHE = {}


def _fetch_dvol_rows(currency, days):
    """Raw DVOL rows [[ts, o, h, l, c], ...] or [] on failure."""
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    start = now_ms - days * 86400 * 1000
    r = requests.get(f"{BASE}/public/get_volatility_index_data",
                     params={"currency": currency, "start_timestamp": start,
                             "end_timestamp": now_ms,
                             "resolution": DVOL_RESOLUTION}, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json().get("result", {}).get("data") or []


def get_dvol_series(currency="BTC", days=DVOL_DAYS):
    """Hourly DVOL as pandas Series indexed by UTC datetime (empty on failure)."""
    try:
        rows = _fetch_dvol_rows(currency, days)
        if not rows:
            return pd.Series(dtype=float)
        idx = pd.to_datetime([r[0] for r in rows], unit="ms", utc=True)
        return pd.Series([r[4] for r in rows], index=idx, dtype=float)
    except Exception as e:
        print(f"[WARN] deribit dvol series failed for {currency}: {e}")
        return pd.Series(dtype=float)


def get_dvol(currency="BTC", days=DVOL_DAYS):
    """Current DVOL + trailing percentile (0-1) over the window."""
    try:
        s = get_dvol_series(currency, days)
        if len(s) < 2:
            return {"dvol": None, "dvol_pct": None}
        current = float(s.iloc[-1])
        pct = float((s <= current).mean())
        print(f"[INFO] deribit {currency} dvol={current:.1f} pct={pct:.2f}")
        return {"dvol": round(current, 2), "dvol_pct": round(pct, 3)}
    except Exception as e:
        print(f"[WARN] deribit dvol failed for {currency}: {e}")
        return {"dvol": None, "dvol_pct": None}


def _get_spot(currency):
    """Deribit index price (btc_usd / eth_usd / sol_usd)."""
    r = requests.get(f"{BASE}/public/get_index_price",
                     params={"index_name": f"{currency.lower()}_usd"}, timeout=TIMEOUT)
    r.raise_for_status()
    return float(r.json()["result"]["index_price"])


def _iv(res):
    """Best IV in vol points: mark_iv, else mid(bid_iv, ask_iv), else None."""
    mark = res.get("mark_iv")
    if mark and mark > 0:
        return float(mark)
    b, a = res.get("bid_iv"), res.get("ask_iv")
    if b and a and b > 0 and a > 0:
        return float((b + a) / 2.0)
    return None


def _interp_iv(points, target):
    """Linear-interpolate IV at |delta|=target; None if not bracketed (no extrapolation)."""
    pts = sorted(points, key=lambda p: p[0])
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    if xs[0] > target + 0.02 or xs[-1] < target - 0.02:
        return None
    return float(np.interp(target, xs, ys))


def get_rr_25d(currency="BTC"):
    """25-delta risk reversal (call IV - put IV, vol points) for nearest weekly expiry."""
    try:
        r = requests.get(f"{BASE}/public/get_instruments",
                         params={"currency": currency, "kind": "option",
                                 "expired": "false"}, timeout=TIMEOUT)
        r.raise_for_status()
        insts = r.json().get("result") or []
        now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
        by_exp = {}
        for i in insts:
            et = i.get("expiration_timestamp")
            if et and et > now_ms:
                by_exp.setdefault(et, []).append(i)
        if not by_exp:
            return {"rr_25d": None, "expiry": None}
        nearest = min(by_exp)
        chain = by_exp[nearest]
        spot = _get_spot(currency)
        chain.sort(key=lambda i: abs(i.get("strike", 0) - spot))
        chain = chain[:MAX_TICKER_CALLS]

        calls, puts = [], []
        for i in chain:
            t = requests.get(f"{BASE}/public/ticker",
                             params={"instrument_name": i["instrument_name"]},
                             timeout=TIMEOUT)
            t.raise_for_status()
            res = t.json().get("result") or {}
            g = res.get("greeks") or {}
            delta = g.get("delta")
            iv = _iv(res)
            if delta is not None and iv is not None:
                if i.get("option_type") == "call":
                    calls.append((abs(float(delta)), iv))
                elif i.get("option_type") == "put":
                    puts.append((abs(float(delta)), iv))
            time.sleep(TICKER_SLEEP)

        if len(calls) < 2 or len(puts) < 2:
            return {"rr_25d": None, "expiry": None}
        call_iv = _interp_iv(calls, RR_DELTA_TARGET)
        put_iv = _interp_iv(puts, RR_DELTA_TARGET)
        if call_iv is None or put_iv is None:
            return {"rr_25d": None, "expiry": None}
        rr = call_iv - put_iv
        expiry_iso = datetime.fromtimestamp(nearest / 1000,
                                            tz=timezone.utc).isoformat()
        print(f"[INFO] deribit {currency} rr_25d={rr:+.2f} expiry={expiry_iso[:10]}")
        return {"rr_25d": round(rr, 2), "expiry": expiry_iso}
    except Exception as e:
        print(f"[WARN] deribit rr_25d failed for {currency}: {e}")
        return {"rr_25d": None, "expiry": None}


def skew_features(currency="BTC"):
    """Merged DVOL + RR dict — always returns a dict, never raises.
    Keys: dvol, dvol_pct, rr_25d, expiry. Failed fields are None."""
    if currency in _CACHE:
        return _CACHE[currency]
    out = {"dvol": None, "dvol_pct": None, "rr_25d": None, "expiry": None}
    out.update(get_dvol(currency))
    out.update(get_rr_25d(currency))
    _CACHE[currency] = out
    return out


if __name__ == "__main__":
    for c in ("BTC", "ETH", "SOL"):
        print(c, skew_features(c))
