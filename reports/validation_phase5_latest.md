# Phase 5 Validation Report

## Scope

This report evaluates the regime-aware trend-following and mean-reversion components over 90 days of free Binance 15-minute candles for BTCUSDT, ETHUSDT, and SOLUSDT. The analysis is research-only. It does not model live fills, liquidation, borrow, funding payments, venue outages, or prop-firm account mechanics.

## Overall Results

| Strategy | Trades | Net return proxy | Win rate | Profit factor | Max drawdown | Decision |
|---|---:|---:|---:|---:|---:|---|
| Trend following | 1,482 | -68.63% | 32.59% | 0.751 | -70.33% | Reject |
| Mean reversion | 84 | -2.83% | 35.71% | 0.871 | -5.61% | Reject |

Neither strategy meets the requested minimum of 50% win rate, 1.3 profit factor, or less than 10% maximum drawdown at the aggregate level.

## Walk-Forward Results

Trend following was negative in **all five** chronological out-of-sample windows. Its median out-of-sample profit factor was 0.655. Mean reversion was positive in only two of five windows, with a median out-of-sample profit factor of 0.926. This is not stable enough to justify promotion.

| Strategy | OOS windows | Positive windows | Median OOS PF | Interpretation |
|---|---:|---:|---:|---|
| Trend following | 5 | 0 | 0.655 | Persistent negative OOS behavior |
| Mean reversion | 5 | 2 | 0.926 | Mixed and below target |

## Purged CPCV

The CPCV analysis uses six chronological folds, two held-out folds per path, and a 48-bar embargo. Outcome intervals must end inside their held-out windows; this avoids counting labels whose outcomes leak across the test boundary.

| Strategy | Labels | CPCV net P05 | CPCV net P50 | CPCV net P95 | Interpretation |
|---|---:|---:|---:|---:|---|
| Trend following | 1,482 | -42.868% | -32.927% | -18.027% | All reported paths are negative |
| Mean reversion | 84 | -3.587% | -0.969% | 2.344% | Median path remains negative |

## Cost Stress

Additional execution-cost stress sharply worsens both strategies. Mean reversion falls from a profit factor of 0.871 at the base assumption to 0.711 with only 5 additional basis points per completed trade. Trend following is already deeply negative before additional costs.

| Strategy | Extra cost | Net return proxy | Profit factor | Max drawdown |
|---|---:|---:|---:|---:|
| Trend following | 0 bps | -68.63% | 0.751 | -70.33% |
| Trend following | 5 bps | -85.06% | 0.630 | -85.42% |
| Mean reversion | 0 bps | -2.83% | 0.871 | -5.61% |
| Mean reversion | 5 bps | -6.83% | 0.711 | -8.77% |
| Mean reversion | 10 bps | -10.67% | 0.584 | -11.92% |

## Promotion Decision

The portfolio remains **research and paper-only**. No strategy is approved for live execution or prop-firm challenge deployment. The next engineering work should focus on diagnosing why the trend component loses after costs, improving the mean-reversion signal only through pre-specified research rules, and validating any revision on a fresh holdout rather than tuning against these results.

The complete machine-readable output is in `validation_phase5_latest.json`.
