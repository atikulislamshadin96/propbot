# Advanced Strategy Research Notes — 2026-08-18

## Decision-relevant findings

Recent research supports using **market microstructure and derivatives-state features** rather than banned retail indicators. A 2026 arXiv study using Binance Futures order books and trades from 2022–2025 reports stable cross-asset predictive feature families involving order-flow imbalance, spreads, liquidity shocks, and VWAP-to-mid deviations, with conservative taker/maker execution tests and explicit flash-crash robustness analysis. This supports an order-flow/liquidity-state signal, but does not guarantee profitability for this repository or current data.

A peer-reviewed study on Bitcoin crash nowcasting finds that order-flow imbalance contributes to crash-risk classification when combined with other ecosystem variables. Its key practical implication is to use imbalance as a **risk/event-state filter**, not as a standalone buy/sell rule.

A 2026 SSRN paper on BTC options risk premia reports that higher-order risk-neutral factors, including variance risk premium and volatility-of-volatility information, contain incremental information for BTC excess returns across horizons. This supports using options-volatility state as a directional-confidence or risk filter, provided the adapter has complete and timestamp-aligned data.

## Proposed one-day strategy

Use a **derivatives-informed liquidity shock continuation/reversal classifier** composed of:

1. Normalized order-flow imbalance and aggressive trade pressure from free public trades/aggregates where available.
2. Open-interest change and liquidation-pressure state from public derivatives endpoints.
3. Options-volatility state from Deribit DVOL and 25-delta risk reversal as a BTC regime/confidence filter.
4. Cross-asset confirmation across BTC, ETH, and SOL rather than an isolated single-asset trigger.
5. Strict next-bar execution, cooldown, max three signals per day, explicit entry/stop/target, and cost stress.

The system must not use RSI, EMA crossover, MACD, Bollinger mean reversion, basic support/resistance, simple breakout logic, ADX as a primary signal, funding arbitrage, or cross-venue basis execution. Existing legacy modules containing these features will not be used as the new signal decision path.

## Evidence limitations

The research sources establish plausible feature families and modeling rationale, not a verified live edge for BTC/ETH/SOL in this repository. The new strategy therefore requires a fresh 90-day backtest, at least three out-of-sample walk-forward windows, purged validation when sample size permits, +5 and +10 bps cost stress, and a fail-closed promotion rule. If any required metric is negative or below the configured floor, paper trading alerts remain disabled.

## Sources

[1] [Explainable Patterns in Cryptocurrency Microstructure](https://arxiv.org/html/2602.00776v1), arXiv, 2026.

[2] [Nowcasting bitcoin’s crash risk with order imbalance](https://pmc.ncbi.nlm.nih.gov/articles/PMC10040314/), Review of Quantitative Finance and Accounting, 2023.

[3] [What Do Crypto Options Tell Us? Risk Premia Implied by BTC Option Prices](https://papers.ssrn.com/sol3/Delivery.cfm/6410838.pdf?abstractid=6410838&mirid=1), SSRN, 2026.
