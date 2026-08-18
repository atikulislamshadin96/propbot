# Funding Data Interfaces

## dYdX

The official dYdX funding documentation states that the protocol calculates a funding rate on an hourly funding tick from one-minute funding-premium samples. The historical-funding client method takes a required market ticker and optional `effectiveBeforeOrAt`, `effectiveBeforeOrAtHeight`, and `limit` parameters. Source: <https://docs.dydx.xyz/concepts/trading/funding> and <https://docs.dydx.xyz/indexer-client/http> (accessed 2026-08-18).

On 2026-08-18, the mainnet Indexer route `https://indexer.dydx.trade/v4/historicalFunding/BTC-USD?limit=100` returned 100 hourly funding observations. The same route accepted an `effectiveBeforeOrAt` cursor for a preceding page. This confirms that the adapter should use the camel-case `historicalFunding` route and paginate backward when it needs more history.

## Adapter safeguards

The implementation must normalize all venue rates to their observed hourly bins before calculating a spread. Any API request that returns an unexpected schema, a non-positive timestamp, or insufficient overlapping history must fail closed and emit no signal.
