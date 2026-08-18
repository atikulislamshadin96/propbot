# Advanced Signal System — Day 1 Delivery Report

**Date:** 2026-08-18
**System:** `propbot`
**Deployment boundary:** Research and validation-gated paper monitoring only

## Executive decision

The one-day implementation is complete, but the system is **not approved for paper trading alerts or live deployment** because the strategy failed every material performance gate on the 90-day real-data validation. The scanner is implemented so that paper-ledger writes and Telegram alerts remain disabled unless the validation report is explicitly `validation_pass: true`.

This is an intentional fail-closed outcome. A strategy that does not demonstrate positive expectancy after costs must not be promoted merely because it produces signals.

## Strategy selected

The chosen strategy is **Aggressive-Flow Liquidity-Shock Continuation**. It uses public Binance Vision spot candles and the taker-buy-volume field as a reproducible aggressive-order-flow proxy. The signal requires an abnormal volume event, strong signed taker-flow imbalance, price movement aligned with the aggressive flow, a bounded intrabar spread proxy, and confirmation from at least two of BTC, ETH, and SOL. It then creates an explicit next-bar paper entry, stop, target, reward/risk, cooldown, and signal-quality score.

The design deliberately excludes RSI, EMA, MACD, Bollinger bands, basic support/resistance, simple breakout rules, ADX as a primary signal, funding arbitrage, and cross-venue basis execution. The research rationale is that order-flow imbalance, liquidity shocks, spreads, and derivatives-state variables are plausible information-state features, but published studies do not establish a profitable edge for this exact implementation or current market sample. [1] [2] [3]

> The research supports a feature family and a testable hypothesis; it does not prove that this repository’s rule has positive future expectancy.

## Implementation delivered

| Artifact | Purpose |
|---|---|
| `advanced_signal.py` | Deterministic non-retail signal engine, quality score, risk levels, and forward outcome evaluator |
| `advanced_data.py` | Free Binance Vision historical loader with timestamp preservation and bounded retries |
| `advanced_backtest.py` | Forward-only synchronized BTC/ETH/SOL backtest with next-bar entry and fees |
| `advanced_validation.py` | Walk-forward, purged-combinatorial robustness, and +5/+10 bps cost-stress gates |
| `advanced_scan.py` | Validation-gated read-only scanner; paper ledger and Telegram are blocked on failure |
| `.github/workflows/advanced-paper.yml` | Serverless GitHub Actions schedule for tests, validation, and gated scanning |
| `tests/test_advanced_signal.py` | Signal, confirmation, risk-level, and forward-evaluation tests |
| `tests/test_advanced_scan.py` | Validation gate tests proving blocked paper/Telegram behavior |

The implementation does not contain exchange authentication, wallet signing, order placement, or live execution capability.

## Real-data validation

The validation used 90 days of synchronized 15-minute Binance Vision spot candles for BTCUSDT, ETHUSDT, and SOLUSDT, producing 8,640 common bars and 136 baseline trades. The evaluator uses next-bar-only outcomes, a conservative stop-first tie break when both stop and target are inside the same bar, and fee stress.

| Fee assumption | Trades | Win rate | Profit factor | Expectancy/trade | Net return | Max drawdown |
|---:|---:|---:|---:|---:|---:|---:|
| 5 bps/side | 136 | 36.76% | 0.686 | −0.0889% | −11.55% | −11.98% |
| 10 bps/side | 136 | 34.56% | 0.457 | −0.1889% | −22.82% | −23.03% |
| 15 bps/side | 136 | 33.09% | 0.301 | −0.2889% | −32.65% | −32.77% |

All three chronological walk-forward windows were negative. Their net returns were −2.15%, −0.83%, and −2.02%, with profit factors of 0.789, 0.904, and 0.694. The 10 purged two-fold combinations had profit-factor median 0.739 and net-return median −3.86%. These results reject the strategy under the stated promotion rules.

| Validation gate | Result |
|---|---|
| At least 50 trades | Pass |
| Win rate above 45% | Fail |
| Profit factor above 1.20 | Fail |
| Positive expectancy | Fail |
| Max drawdown no worse than −7% | Fail |
| Profit factor above 1.00 at +5 bps stress | Fail |
| Profit factor above 1.00 at +10 bps stress | Fail |
| Positive expectancy in every walk-forward window | Fail |
| Positive purged-CPCV median | Fail |

## Paper trading and Telegram status

Paper trading was **not started as an active signal stream**, and Telegram alerts are **not active**, because the validation verdict is false. The scheduled workflow is present and can run the read-only scanner, but it will report `BLOCKED_VALIDATION_FAIL`, record no paper candidates, and send zero Telegram alerts. This prevents the user from interpreting unvalidated signals as an approved strategy.

The workflow is free to run under GitHub Actions and can be re-enabled for research monitoring without changing the fail-closed policy. Any future paper activation requires a new validation report with `validation_pass: true`; live deployment would require a separate authorization and additional execution-quality evidence.

## Reproduction

```bash
python3 advanced_backtest.py --days 90 --fee-bps 5
python3 advanced_validation.py --days 90
python3 advanced_scan.py
python3 -m unittest discover -s tests -p 'test_*.py'
python3 audit_behavior.py
```

The repository checks passed: 42 unit tests, 5 behavioral-audit checks, Python compilation, and whitespace validation.

## References

[1]: https://arxiv.org/html/2602.00776v1 "Explainable Patterns in Cryptocurrency Microstructure, arXiv, 2026"

[2]: https://pmc.ncbi.nlm.nih.gov/articles/PMC10040314/ "Nowcasting bitcoin’s crash risk with order imbalance, Review of Quantitative Finance and Accounting, 2023"

[3]: https://papers.ssrn.com/sol3/Delivery.cfm/6410838.pdf?abstractid=6410838&mirid=1 "What Do Crypto Options Tell Us? Risk Premia Implied by BTC Option Prices, SSRN, 2026"

[4]: https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/info-endpoint "Hyperliquid Info Endpoint Documentation"

[5]: https://docs.deribit.com/api-reference/market-data/public-ticker "Deribit Public Ticker Documentation"
