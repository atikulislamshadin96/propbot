# PropBot Audit and Funding-Divergence Research Update

## Scope

This change set verifies and repairs four previously identified implementation defects, then replaces the scheduled signal workflow with a **research and paper-candidate-only** cross-venue funding-divergence scanner. It contains no trading keys, order placement, leverage configuration, or exchange execution code.

## Confirmed repairs

| Area | Confirmed issue | Repair | Regression coverage |
|---|---|---|---|
| Risk sizing | ATR-derived stop could exceed the stated risk cap | Clamp stop risk to `MAX_RISK` | `RiskCapTests` |
| Feature parity | Scanner passed funding features under inconsistent names | Shared feature normalization used by live and research paths | `audit_behavior.py` |
| Validation | Purged cross-validation retained embargoed/overlapping observations | Explicitly remove all overlap and embargo rows from training folds | `PurgeTests` |
| Funding history | Hyperliquid pagination could stall on string timestamps | Normalize timestamps before moving the cursor backward | `FundingPaginationTests` |

## Funding-divergence research rule

The scanner normalizes Hyperliquid and dYdX funding observations to hourly bins and calculates `Hyperliquid funding − dYdX funding`. It creates a paper candidate only when the spread has an absolute trailing z-score of at least `2.5` and its expected eight-hour gross funding exceeds `37.5` basis points, representing a `30`-basis-point round-trip friction estimate with a `1.25×` buffer.

The rule is intentionally conservative. Candidate records identify a possible receive-funding leg but explicitly exclude basis movement, execution, borrow, margin, liquidation, settlement, capacity, and venue risk. They are research artifacts—not trading instructions or investment recommendations.

## Public data and validation

dYdX documentation specifies hourly funding ticks and a public historical-funding method. The implementation uses the verified mainnet Indexer route `https://indexer.dydx.trade/v4/historicalFunding/{TICKER}` with backward pagination. Source details and safeguards are recorded in [data_sources.md](data_sources.md).

The 2026-08-18 90-day public-data event study obtained `2,160` overlapping BTC hourly observations. Under the current strict threshold, it found **zero** qualifying counterfactual events. This is a valid negative result: the system fails closed rather than extrapolating a return claim.

## Operations

The scheduled research workflow now runs every four hours and only executes `funding_scan.py`. The weekly validation workflow runs the deterministic regression suite plus the public funding scan and event study. Both workflows produce reports; neither is capable of placing orders.

## Verification

Run locally:

```bash
python3 audit_behavior.py
python3 run_regression_tests.py
python3 funding_scan.py
python3 funding_event_study.py
```
