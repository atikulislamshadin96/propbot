# PropBot validation report — 2026-08-18

## Executive conclusion

The repository is **software-test ready for read-only research and paper-candidate scanning**, but it is **not statistically or operationally ready for live trading or a prop-firm challenge**. The requested 365-day divergence backtest produced zero qualifying events, so win rate, expectancy, profit factor, Monte Carlo ruin, and CPCV percentiles are undefined. This is an insufficient-evidence result, not a positive edge.

> I am an AI, not a licensed financial advisor—this is analysis, not guaranteed advice; investing carries risk you bear.

## Changes verified

| Area | Result |
|---|---|
| Risk cap | Existing capped stop-distance regression passes; the configured maximum is treated as a cap rather than a floor. |
| Live/backtest feature parity | Existing behavior audit confirms the Hyperliquid funding z-score is passed through the live feature path. |
| Purged validation | Existing purge/embargo regression passes; the strategy-aware CPCV runner now protects overlapping labels and forward embargo windows. |
| Hyperliquid pagination | String timestamp regression passes after numeric normalization. |
| dYdX adapter | Mocked schema tests pass; live read-only health check returned market metadata for 296 markets and 24 one-day BTC historical rows. |
| Shared signal | 16 deterministic tests pass, including both divergence directions, missing-history fail-closed behavior, and cost gating. |

## Public-data results

The 90-day scan obtained `2,160` overlapping BTC hourly observations and scored `2,089` observations. Under `|z| >= 2.5` and a buffered expected eight-hour gross-funding threshold of `37.5` basis points, it produced no candidate. The 90-day counterfactual event study also recorded zero qualifying events.

The requested 365-day backtest obtained `8,757` aligned hourly bars after fetching approximately 364 days of Hyperliquid history. It produced zero qualifying events. Strategy-aware purged validation therefore emitted an explicit insufficient-evidence report and did not calculate performance percentiles.

## Deployment decision

The current safe deployment is the four-hour **research/paper-candidate workflow**. It produces JSON and Markdown reports, optionally sends Telegram messages that say “No order was sent,” and contains no exchange-order capability. Live deployment is blocked because there is no demonstrated out-of-sample edge, no paired-leg accounting in the existing paper database, and no measurement of basis, slippage, fills, margin, liquidation, settlement, venue outages, or capacity.

| Criterion | Required | Observed | Decision |
|---|---:|---:|---|
| CPCV P50 expectancy | > 0.05% / defined sample | Undefined; zero events | Fail closed |
| Monte Carlo ruin | < 10% | Undefined; zero events | Fail closed |
| Static OOS net | > 0% | Undefined; zero events | Fail closed |
| Profit factor | > 1.3 | Undefined; zero events | Fail closed |
| Paper stability | 1–30 days | Not established by this run | Do not promote |

## Primary public endpoints checked

The adapter uses the dYdX Indexer perpetual-market endpoint at [`/v4/perpetualMarkets`](https://indexer.dydx.trade/v4/perpetualMarkets) and historical funding endpoint at [`/v4/historicalFunding/BTC-USD`](https://indexer.dydx.trade/v4/historicalFunding/BTC-USD). Hyperliquid historical funding is obtained through its public information API at [`api.hyperliquid.xyz/info`](https://api.hyperliquid.xyz/info). These sources are public market-data interfaces; their availability does not establish execution quality or economic profitability.

## Next gate

The next responsible step is a longer paper-only observation period with paired-leg accounting and explicit basis/execution measurements. The system should not be connected to live trading credentials until the stated statistical gates are met on enough non-overlapping, forward-only observations and the operational controls have been independently reviewed.

## References

[1]: https://indexer.dydx.trade/v4/perpetualMarkets "dYdX Indexer perpetual markets endpoint"
[2]: https://indexer.dydx.trade/v4/historicalFunding/BTC-USD "dYdX Indexer BTC-USD historical funding endpoint"
[3]: https://api.hyperliquid.xyz/info "Hyperliquid public information endpoint"
