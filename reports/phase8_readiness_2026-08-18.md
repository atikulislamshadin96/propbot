# Phase 8 Readiness Decision

## Executive Decision

**Status: NOT APPROVED for live prop-firm challenge deployment.**

The repository now contains a research-grade and operationally safer paper-trading foundation, but the measured strategy evidence does not support the requested success criteria of greater than 50% win rate, greater than 1.3 profit factor, and less than 10% maximum drawdown. Enabling live execution would therefore be an unsupported financial-risk escalation.

The active deployment boundary is **read-only research plus paper monitoring**. No exchange credentials, order API, wallet signing, or live order path has been added.

## Completed Work

| Phase | Result | Evidence |
|---|---|---|
| 1. Threshold and frequency validation | Completed | Strict economic gate remains unchanged; relaxed profiles are research-only. |
| 2. Independent strategies | Completed | Trend, mean-reversion, and funding-divergence registry with conflict metadata. |
| 3. Regime awareness | Completed | Trend/range/extreme-volatility/missing-data classifier with fail-closed filtering. |
| 4. Risk controls | Completed | Position caps, open-risk cap, daily loss, drawdown, consecutive-loss, cooldown, and duplicate-symbol gates. |
| 5. Honest validation | Completed | Forward-only backtest, walk-forward windows, purged CPCV with 48-bar embargo, and cost stress. |
| 6. Paper monitoring | Operationalized, not yet statistically complete | Four-hour GitHub Actions monitor, candle freshness, ledger, holding-time, and paper-only execution proxies. Current ledger has zero closed paper trades. |
| 7. Prop-rule guard | Completed | Generic configurable paper-only rule evaluator and kill-switch report. It does not represent a named firm’s current rulebook. |
| 8. Readiness decision | Completed | This report. |

## Measured Strategy Evidence

The 90-day regime-aware test used free 15-minute candles for BTCUSDT, ETHUSDT, and SOLUSDT. These are research proxies, not live execution results.

| Strategy | Trades | Net return proxy | Win rate | Profit factor | Max drawdown | Walk-forward result | CPCV P50 net |
|---|---:|---:|---:|---:|---:|---|---:|
| Trend following | 1,482 | -68.63% | 32.59% | 0.751 | -70.33% | 0/5 positive windows | -32.93% |
| Mean reversion | 84 | -2.83% | 35.71% | 0.871 | -5.61% | 2/5 positive windows | -0.97% |

The funding-divergence path still has no qualifying economically gated events in the available BTC history. A diagnostic z-score-only rule produced observations, but its expected gross funding was far below the active cost buffer, so it was not promoted.

Cost stress is unfavorable. Mean reversion’s profit factor fell from 0.871 at the base assumption to 0.711 with five additional basis points per completed trade. Trend following was already negative before additional stress.

## Paper and Data Status

The current read-only monitor reports fresh public Binance candles for BTCUSDT, ETHUSDT, and SOLUSDT, with zero open positions and zero closed paper trades at the time of the latest run. Because no paper trade has yet completed, execution-quality statistics such as realized slippage, fill probability, and signal-to-fill behavior are **not established**.

The generic paper-rule report is currently `ACTIVE_PAPER` with no breached limits, but this only means that the empty ledger has not violated its configured limits. It is not evidence of profitability, robustness, or a successful challenge.

## Promotion Gates Still Unmet

Before any live or challenge-account integration could be considered, the project would need a named firm’s verified current rules, a legally and operationally appropriate execution design, a sufficiently long out-of-sample paper record, observed fill and slippage data, paired-leg accounting for funding trades, reconciliation, venue-outage behavior, margin/liquidation controls, credential isolation, and independently reviewed kill switches. The statistical targets would also need to be met on fresh data without selecting parameters on the final holdout.

The present evidence fails those gates. The correct action is to continue paper monitoring and research, not to deploy capital.

## Repository State

The verified work is on branch `feat/divergence-signal-integration`. The latest risk and prop-rule implementation commit is `6fe5496`; the earlier walk-forward and stress validation commit is `77751c4`. The draft pull request remains the review boundary: [PropBot draft PR #1](https://github.com/atikulislamshadin96/propbot/pull/1).

> This report is an engineering and research readiness assessment, not investment advice or a guarantee of trading performance.
