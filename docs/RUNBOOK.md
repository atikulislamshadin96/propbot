# Operations runbook

## Normal operation

GitHub Actions runs the research scan every four hours and the validation refresh weekly. Each scan should create or update `reports/funding_scan_latest.json`, `reports/funding_scan_latest.md`, and `keepalive.txt`. A paper candidate is an alerting event only; it is not an instruction to open a position.

## Required secrets

`TG_TOKEN` and `TG_CHAT_ID` are optional and are used only for paper-only Telegram messages. No exchange credential is expected or required. Do not store private keys, wallet secrets, or order credentials in repository files or Actions logs.

## Failure behavior

Malformed data, unavailable endpoints, insufficient overlap, invalid rates, or missing history must result in no candidate. A failed workflow should be investigated rather than bypassed by replacing missing data with zero. The dYdX adapter should be checked first for HTTP status, response schema, rate-limit response headers, and pagination progress.

## Monitoring checklist

Review the latest report for observation count, scored count, current spread, z-score, candidate mode, and the explicit safety boundary. Check that the workflow completed, the heartbeat timestamp advanced, and no unexpected files were committed. For any candidate, independently review venue status, liquidity, funding schedule, basis movement, and operational feasibility; this repository does not model those risks.

## Promotion gate

No live trading deployment is authorized by this repository. Before any future execution layer could be considered, the project would need a separate design for paired-leg positions, position matching, fee and slippage measurement, basis and mark-price accounting, margin/liquidation controls, venue outage handling, reconciliation, kill switches, credential isolation, and a long enough out-of-sample paper record. All of the stated statistical gates must be met on honest, leakage-controlled data; zero-event or insufficient-history results fail closed.
