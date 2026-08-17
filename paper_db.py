import json
import os
import time
from datetime import datetime, timezone, timedelta

DATA = "data"
TRADES = os.path.join(DATA, "trades.jsonl")
SIGNALS = os.path.join(DATA, "signals.jsonl")


def _now():
    return datetime.now(timezone.utc).isoformat()


def _read(path):
    if not os.path.exists(path):
        return []
    out = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                try:
                    out.append(json.loads(line))
                except Exception:
                    continue
    return out


def _append(path, obj):
    os.makedirs(DATA, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")


def log_signal(sig):
    _append(SIGNALS, {"ts": _now(), **sig})


def open_trade(sig, risk_pct):
    t = {
        "id": int(time.time() * 1000),
        "ts": _now(),
        "status": "open",
        "exit": None,
        "pnl_pct": None,
        "closed_ts": None,
        "risk_pct": risk_pct,
        **{k: sig[k] for k in ("side", "entry", "sl", "tp", "score",
                                "regime", "s_zone", "s_flow", "s_crowd", "s_gate")
           if k in sig}
    }
    if sig.get("zone"):
        t["zone"] = sig["zone"]
    _append(TRADES, t)
    return t["id"]


def open_trades():
    return [t for t in _read(TRADES) if t.get("status") == "open"]


def trades_today(max_positions=2):
    now = datetime.now(timezone.utc).date()
    closed = [t for t in _read(TRADES)
              if t.get("status") in ("tp", "sl")
              and t.get("closed_ts")]
    today_closed = []
    for t in closed:
        try:
            dt = datetime.fromisoformat(t["closed_ts"]).date()
            if dt == now:
                today_closed.append(t)
        except Exception:
            continue
    return today_closed


def daily_pnl_pct():
    return sum(t.get("pnl_pct", 0.0) for t in trades_today())


def last_trade_time():
    closed = [t for t in _read(TRADES)
              if t.get("status") in ("tp", "sl") and t.get("closed_ts")]
    if not closed:
        return None
    closed.sort(key=lambda x: x["closed_ts"])
    return closed[-1]["closed_ts"]


def check_cooldown(cooldown_min=30):
    last = last_trade_time()
    if last is None:
        return True
    try:
        last_dt = datetime.fromisoformat(last)
        return (datetime.now(timezone.utc) - last_dt) >= timedelta(minutes=cooldown_min)
    except Exception:
        return True


def check_and_close(candle_high, candle_low, fee_pct=0.05):
    changed = []
    trades = _read(TRADES)
    for t in trades:
        if t.get("status") != "open":
            continue
        if t["side"] == "BUY":
            if candle_low <= t["sl"]:
                exit_px, res = t["sl"], "sl"
            elif candle_high >= t["tp"]:
                exit_px, res = t["tp"], "tp"
            else:
                continue
        else:
            if candle_high >= t["sl"]:
                exit_px, res = t["sl"], "sl"
            elif candle_low <= t["tp"]:
                exit_px, res = t["tp"], "tp"
            else:
                continue
        t["status"] = res
        t["exit"] = exit_px
        pnl = ((exit_px - t["entry"]) / t["entry"] * 100
               if t["side"] == "BUY"
               else (t["entry"] - exit_px) / t["entry"] * 100)
        t["pnl_pct"] = round(pnl - fee_pct, 3)
        t["closed_ts"] = _now()
        changed.append(t)

    if changed:
        with open(TRADES, "w", encoding="utf-8") as f:
            for r in trades:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
    return changed


def daily_report_summary():
    closed = [t for t in _read(TRADES) if t.get("status") in ("tp", "sl")]
    today = trades_today()
    n_all = len(closed)
    wins_all = sum(1 for t in closed if t.get("pnl_pct", 0) > 0)
    n_today = len(today)
    return {
        "total_trades": n_all,
        "total_wins": wins_all,
        "total_wr": round(100 * wins_all / max(n_all, 1), 1),
        "today_trades": n_today,
        "today_pnl": round(daily_pnl_pct(), 2),
    }
