# Phase 1 — Threshold Relaxation and Signal Frequency

Mode: **research-only; no orders are sent.**
Coin: `BTC` | panel: `8757` | scored: `8543`

## Summary

| Rule | Raw triggers | Non-overlapping entries | Entries/week |
|---|---:|---:|---:|
| Current rule (z + 37.5 bps cost gate) | 0 | 0 | 0.0 |
| z-score only (diagnostic) | 314 | 121 | 2.3789 |
| Adaptive threshold | 0 | 0 | 0.0 |
| Adaptive + economic cost gate | 0 | 0 | 0.0 |

## Interpretation

A relaxed threshold can increase alerts, but an alert is not evidence of positive expectancy. The economic-cost-gated line is the relevant safety check; any threshold that increases frequency only by admitting observations below estimated costs remains research-only.
Expected gross funding quantiles are included in the JSON report to show how much of the zero-signal problem comes from economic magnitude rather than z-score rarity.

## Threshold grid

| Z threshold | Expected gross funding threshold (bps) | Entries/week | Economic gate applied |
|---:|---:|---:|---|
| 1.50 | 15.0 | 0.0393 | No |
| 1.50 | 20.0 | 0.0000 | No |
| 1.50 | 25.0 | 0.0000 | No |
| 1.50 | 30.0 | 0.0000 | No |
| 1.50 | 35.0 | 0.0000 | No |
| 1.75 | 15.0 | 0.0393 | No |
| 1.75 | 20.0 | 0.0000 | No |
| 1.75 | 25.0 | 0.0000 | No |
| 1.75 | 30.0 | 0.0000 | No |
| 1.75 | 35.0 | 0.0000 | No |
| 2.00 | 15.0 | 0.0393 | No |
| 2.00 | 20.0 | 0.0000 | No |
| 2.00 | 25.0 | 0.0000 | No |
| 2.00 | 30.0 | 0.0000 | No |
| 2.00 | 35.0 | 0.0000 | No |
| 2.25 | 15.0 | 0.0393 | No |
| 2.25 | 20.0 | 0.0000 | No |
| 2.25 | 25.0 | 0.0000 | No |
| 2.25 | 30.0 | 0.0000 | No |
| 2.25 | 35.0 | 0.0000 | No |
| 2.50 | 15.0 | 0.0393 | No |
| 2.50 | 20.0 | 0.0000 | No |
| 2.50 | 25.0 | 0.0000 | No |
| 2.50 | 30.0 | 0.0000 | No |
| 2.50 | 35.0 | 0.0000 | No |

## Limitations

The frequency table measures historical trigger counts only. It does not establish win rate, profit factor, drawdown, or prop-firm rule compliance. Those require forward-only outcomes and execution-aware paper records.
