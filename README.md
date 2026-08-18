# PropBot Genesis v3

PropBot is a **read-only crypto funding-divergence research and paper-candidate system**. It compares hourly Hyperliquid and dYdX perpetual funding observations, applies a trailing z-score and cost gate, writes auditable reports, and can send Telegram notifications that explicitly state that no order was sent.

> This repository does not contain exchange credentials, wallet functionality, leverage configuration, or order-placement code. It is not a trading recommendation and does not prove profitability or prop-firm eligibility.

## Current decision rule

The system computes `spread = Hyperliquid hourly funding − dYdX hourly funding`. A candidate requires at least `72` hours of valid overlap, an absolute trailing z-score of at least `2.5`, and expected eight-hour gross funding of at least `37.5` basis points after a buffered fixed-cost estimate. A positive spread produces a `SHORT_HL_LONG_DYDX` paper candidate; a negative spread produces `LONG_HL_SHORT_DYDX`.

The signal is implemented once in `signals_v3.py` and reused by the research scan and the counterfactual funding backtest. The legacy single-instrument 15-minute sweep scanner remains available only through `LEGACY_SCAN=1` for comparison and is not the scheduled production path.

## Repository layout

| Path | Purpose |
|---|---|
| `signals_v3.py` | Shared fail-closed divergence signal engine |
| `funding_data.py` | Hyperliquid/dYdX historical normalization |
| `dydx_data.py` | dYdX current market/funding adapter and health checks |
| `funding_scan.py` | Four-hour report and optional Telegram notification |
| `divergence_backtest.py` | Funding-only counterfactual event backtest |
| `backtest_v2.py` | Strategy-aware CLI; divergence is the default, legacy is opt-in |
| `purged_validation.py` | Overlap/embargo-safe CPCV for available labels |
| `paper_db.py` | Existing single-leg paper store, retained for legacy compatibility |
| `.github/workflows/scan.yml` | Four-hour read-only research scan |
| `.github/workflows/backtest.yml` | Weekly regression and public-data refresh |
| `docs/` | Audit findings, data-source notes, architecture, and runbook |
| `tests/` | Deterministic unit and regression tests |

## Local verification

```bash
python3 audit_behavior.py
python3 run_regression_tests.py
python3 -m py_compile *.py
python3 funding_scan.py
python3 funding_event_study.py
python3 backtest_v2.py --days 365 --coin BTC
python3 purged_validation.py --days 365 --coin BTC
```

The public-data commands require network access. The deterministic tests do not call exchanges. A result with zero qualifying events is an insufficient-evidence result, not a failed software test and not evidence of positive expectancy.

## GitHub Actions

The scheduled scan runs at minute 15 of every fourth hour and commits only generated research artifacts. The weekly workflow runs the deterministic test suite and refreshes the public funding reports. Both workflows are designed to fail closed on malformed or unavailable data. Telegram credentials, if used, are read from repository secrets named `TG_TOKEN` and `TG_CHAT_ID`; they are used only for paper-only notifications.

Do not add exchange API keys or order code to this repository unless the system is redesigned with paired-leg accounting, explicit risk controls, independent paper validation, and a separately approved deployment process. A prop-firm challenge target cannot be guaranteed by code or backtest statistics.
