"""Validation-gated paper scanner for the advanced flow-shock strategy.

This command is read-only with respect to exchanges. It may append paper
candidates locally only when the validation report is PASS and the explicit
paper flag is enabled. Telegram is likewise gated by the same validation flag.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

import requests

import config_v2 as cfg
from advanced_signal import AdvancedSignalConfig, generate_signals
from binance_data import klines

REPORT = Path("reports/advanced_validation_latest.json")
SCAN_REPORT = Path("reports/advanced_scan_latest.json")
PAPER_LEDGER = Path("data/advanced_paper_signals.jsonl")


def validation_pass() -> bool:
    try:
        return bool(json.loads(REPORT.read_text()).get("validation_pass", False))
    except (OSError, ValueError, TypeError):
        return False


def send_telegram(message: str) -> bool:
    if not validation_pass() or os.getenv("ENABLE_ADVANCED_TELEGRAM", "0") != "1":
        return False
    if not (cfg.TG_TOKEN and cfg.TG_CHAT_ID):
        return False
    try:
        response = requests.post(
            f"https://api.telegram.org/bot{cfg.TG_TOKEN}/sendMessage",
            json={"chat_id": cfg.TG_CHAT_ID, "text": message[:4000]}, timeout=10,
        )
        response.raise_for_status()
        return True
    except requests.RequestException:
        return False


def append_paper(signal: Dict[str, Any]) -> None:
    PAPER_LEDGER.parent.mkdir(exist_ok=True)
    with PAPER_LEDGER.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"logged_at": datetime.now(timezone.utc).isoformat(), **signal}) + "\n")


def run() -> Dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat()
    verdict = validation_pass()
    panel = {}
    errors = {}
    for symbol in cfg.SYMBOLS:
        try:
            panel[symbol] = klines(symbol, cfg.INTERVAL, 500)
        except Exception as exc:
            errors[symbol] = str(exc)
    candidates = generate_signals(panel, AdvancedSignalConfig(), now_ts=int(datetime.now(timezone.utc).timestamp() * 1000)) if panel else []
    recorded = []
    alerts = 0
    if verdict and os.getenv("ENABLE_ADVANCED_PAPER", "0") == "1":
        for signal in candidates:
            payload = signal.to_dict()
            append_paper(payload)
            recorded.append(payload)
            if send_telegram(
                f"ADVANCED PAPER SIGNAL {signal.side} {signal.symbol}\n"
                f"entry={signal.entry} sl={signal.stop_loss} tp={signal.take_profit}\n"
                f"quality={signal.quality_score} breadth={signal.breadth}"
            ):
                alerts += 1
    result = {"generated_at": now, "strategy": "aggressive_flow_liquidity_shock",
              "validation_pass": verdict, "paper_enabled": os.getenv("ENABLE_ADVANCED_PAPER", "0") == "1",
              "telegram_enabled": os.getenv("ENABLE_ADVANCED_TELEGRAM", "0") == "1",
              "candidates_seen": [s.to_dict() for s in candidates],
              "paper_recorded": recorded, "telegram_alerts_sent": alerts, "errors": errors,
              "deployment_status": "ACTIVE_PAPER" if verdict else "BLOCKED_VALIDATION_FAIL"}
    SCAN_REPORT.parent.mkdir(exist_ok=True)
    SCAN_REPORT.write_text(json.dumps(result, indent=2))
    print(json.dumps({k: result[k] for k in ("validation_pass", "candidates_seen", "paper_recorded", "telegram_alerts_sent", "deployment_status")}, indent=2))
    return result


if __name__ == "__main__":
    run()
