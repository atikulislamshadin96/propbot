"""Generate a public-data funding-divergence research report; never places orders."""
from __future__ import annotations

import json
import os
from pathlib import Path

import requests

import config_v2 as cfg
from funding_data import normalized_funding_series
from funding_strategy import divergence_panel, paper_candidate


REPORT_DIR = Path("reports")


def send_telegram(message: str) -> None:
    """Send an optional paper-only alert; missing credentials are a no-op."""
    token = os.getenv("TG_TOKEN", "")
    chat_id = os.getenv("TG_CHAT_ID", "")
    if not token or not chat_id:
        return
    try:
        response = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": message[:4000]},
            timeout=10,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        print(f"[WARN] Telegram notification failed: {exc}")


def main() -> None:
    """Fetch, score, report, and optionally notify a paper candidate."""
    REPORT_DIR.mkdir(exist_ok=True)
    coin = cfg.FUNDING_ACTIVE_COIN
    panel = normalized_funding_series(coin, cfg.FUNDING_HISTORY_DAYS)
    scored = divergence_panel(panel)
    candidate = paper_candidate(panel)
    payload = {
        "mode": "RESEARCH_AND_PAPER_CANDIDATES_ONLY",
        "coin": coin,
        "overlapping_hourly_observations": int(len(panel)),
        "scored_observations": int(len(scored)),
        "candidate": candidate,
        "order_execution_enabled": False,
    }
    (REPORT_DIR / "funding_scan_latest.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    latest = scored.iloc[-1] if not scored.empty else None
    markdown = [
        "# Funding-Divergence Research Scan",
        "",
        "Mode: **research and paper candidates only; no orders are sent.**",
        f"Coin: `{coin}` | overlapping hourly observations: `{len(panel)}` | scored: `{len(scored)}`",
    ]
    if latest is not None:
        markdown.append(f"Latest spread: `{latest['spread']:.8f}` | z-score: `{latest['spread_z']:.2f}`")
    markdown.extend(
        [
            "",
            "## Outcome",
            "```json",
            json.dumps(candidate or {"candidate": None, "reason": "No cost-gated extreme met the paper-candidate criteria."}, indent=2),
            "```",
            "",
            "## Safety boundary",
            "This report is not an order instruction. Basis, fills, position matching, funding changes, borrow, margin, liquidation, settlement, capacity, and venue risk are not modeled.",
        ]
    )
    (REPORT_DIR / "funding_scan_latest.md").write_text("\n".join(markdown) + "\n", encoding="utf-8")

    if candidate:
        send_telegram(
            f"PAPER-ONLY funding candidate {candidate['side']} {coin}\n"
            f"z={candidate['spread_z']:.2f} | expected net before basis risk="
            f"{candidate['expected_net_bps_before_basis_risk']:.1f} bps\n"
            "No order was sent."
        )
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
