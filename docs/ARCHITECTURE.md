# Architecture

```mermaid
flowchart LR
    H[Hyperliquid public funding history] --> N[Hourly normalization]
    D[dYdX Indexer public funding history] --> N
    N --> P[Spread and trailing z-score]
    P --> S[signals_v3 shared fail-closed rule]
    S --> R[Research JSON/Markdown reports]
    S --> T[Optional Telegram paper-only alert]
    R --> G[GitHub Actions artifact commit]

    L[Legacy 15m single-leg scanner] -. LEGACY_SCAN=1 only .-> X[Compatibility path]
    X -. not scheduled .-> Q[No production decision authority]
```

The scheduled path is intentionally **read-only**. The only authoritative decision function is `signals_v3.evaluate_divergence()`, which requires valid funding observations, sufficient history, an extreme z-score, and a buffered expected-funding-cost gate. It returns a paper candidate with two conceptual venue legs; it does not generate a stop, take-profit, leverage, margin, or order payload.

Historical data is aligned to hourly bins using the common overlap only. The code does not forward-fill one venue across a missing observation from the other venue. dYdX responses are checked for expected fields and paginated backward through `effectiveBeforeOrAt`; Hyperliquid timestamps are normalized before cursor arithmetic.

The current paper database models a single directional instrument and is therefore not used to represent a paired funding candidate. This separation prevents a misleading one-leg PnL record from being interpreted as a delta-neutral result.
