"""Generate a public-data funding-divergence research report; never places or simulates orders."""
import json
from pathlib import Path

import config_v2 as cfg
from funding_data import normalized_funding_series
from funding_strategy import divergence_panel, paper_candidate


REPORT_DIR = Path("reports")


def main():
    REPORT_DIR.mkdir(exist_ok=True)
    panel = normalized_funding_series(cfg.FUNDING_ACTIVE_COIN, cfg.FUNDING_HISTORY_DAYS)
    scored = divergence_panel(panel)
    candidate = paper_candidate(panel)
    payload = {
        "mode": "RESEARCH_AND_PAPER_CANDIDATES_ONLY",
        "coin": cfg.FUNDING_ACTIVE_COIN,
        "overlapping_hourly_observations": int(len(panel)),
        "scored_observations": int(len(scored)),
        "candidate": candidate,
    }
    (REPORT_DIR / "funding_scan_latest.json").write_text(json.dumps(payload, indent=2) + "\n")
    latest = scored.iloc[-1] if not scored.empty else None
    markdown = ["# Funding-Divergence Research Scan", "", "Mode: **research and paper candidates only; no orders are sent.**", ""]
    markdown.append(f"Coin: `{cfg.FUNDING_ACTIVE_COIN}` | overlapping hourly observations: `{len(panel)}` | scored: `{len(scored)}`")
    if latest is not None:
        markdown.append(f"Latest spread: `{latest['spread']:.8f}` | z-score: `{latest['spread_z']:.2f}`")
    markdown.append("")
    markdown.append("## Outcome")
    markdown.append("```json")
    markdown.append(json.dumps(candidate or {"candidate": None, "reason": "No cost-gated extreme met the paper-candidate criteria."}, indent=2))
    markdown.append("```")
    (REPORT_DIR / "funding_scan_latest.md").write_text("\n".join(markdown) + "\n")
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
