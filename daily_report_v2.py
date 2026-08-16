# ============================================================
# daily_report_v2.py — Daily Telegram report + GO/STOP gauge
# ============================================================
import os, requests
from datetime import datetime, timezone
import config_v2 as cfg
import paper_db as db

def send_telegram(msg):
    if not (cfg.TG_TOKEN and cfg.TG_CHAT_ID):
        return
    try:
        requests.post(f"https://api.telegram.org/bot{cfg.TG_TOKEN}/sendMessage",
                      json={"chat_id": cfg.TG_CHAT_ID, "text": msg[:4000],
                            "parse_mode": "Markdown"}, timeout=10)
    except Exception:
        pass

def go_stop_gauge():
    """50-trade rolling GO/STOP check"""
    closed = [t for t in db._read(db.TRADES)
              if t.get("status") in ("tp", "sl")]
    last = closed[-50:]
    if len(last) < 20:
        return "⏳ INSUFFICIENT DATA", None
    pnls = [t["pnl_pct"] for t in last]
    wins = [p for p in pnls if p > 0]
    wr = 100 * len(wins) / len(pnls)
    exp = sum(pnls) / len(pnls)
    pf_num = sum(p for p in pnls if p > 0)
    pf_den = abs(sum(p for p in pnls if p <= 0))
    pf = pf_num / pf_den if pf_den > 0 else float("inf")

    go = wr >= 45 and exp >= 0.1 and pf >= 1.2
    status = "🟢 GO" if go else "🔴 STOP"
    return status, {"wr": round(wr, 1), "exp": round(exp, 2), "pf": round(pf, 2)}

def build():
    s = db.daily_report_summary()
    gauge, g = go_stop_gauge()
    lines = [f"📊 *PropBot Daily Report*",
             f"Total: {s['total_trades']} trades | WR {s['total_wr']}%",
             f"Today: {s['today_trades']} trades | PnL {s['today_pnl']:+.2f}%",
             f"Gauge: {gauge}"]
    if g:
        lines.append(f"WR {g['wr']}% | Exp {g['exp']:+.2f}% | PF {g['pf']}")
    msg = "\n".join(lines)

    os.makedirs("reports", exist_ok=True)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    with open(f"reports/daily_{today}.md", "w") as f:
        f.write(msg.replace("*", ""))
    send_telegram(msg)
    print(msg)

if __name__ == "__main__":
    build()
