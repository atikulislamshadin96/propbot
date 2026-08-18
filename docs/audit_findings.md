# Audit findings — 2026-08-18

## Repository state

The public `atikulislamshadin96/propbot` repository was cloned at commit `8eb4ce9` on the `main` branch. The existing deterministic audit and regression suites pass: 5/5 behavioral checks and 10/10 unit tests.

## Verified repairs already present

The repository already contains a capped stop-distance helper using `min(ATR distance, entry price × MAX_RISK_PCT)`, explicit live feature parity for `hl_funding_z`, purge/embargo filtering in `purged_validation.py`, and Hyperliquid timestamp normalization before cursor advancement.

## Critical integration gap

The active decision path is still `signals_v2.evaluate()` from both `scan.py` and `backtest_v2.py`. It requires the legacy 15-minute `sweep_res` structure, only emits a single-instrument `BUY`/`SELL`, and does not consume the new Hyperliquid-versus-dYdX spread or `spread_z` as the decision rule. The new funding-divergence code is isolated to research reports.

## Operational boundary

The current scheduled workflows run a four-hour research scan and a weekly research/validation refresh. They do not have exchange-order code. The paper database models a single directional leg and therefore cannot faithfully represent a paired Hyperliquid/dYdX funding trade without a schema extension. The implementation must remain fail-closed and paper/research-only until paired-leg accounting, basis risk, venue availability, and a sufficiently long positive out-of-sample record are demonstrated.

## Validation baseline

The repository's notes report 2,160 overlapping BTC hourly observations in the latest 90-day event study and zero qualifying events under the strict z-score and cost gates. This is a negative/insufficient-evidence result, not evidence of profitability.
