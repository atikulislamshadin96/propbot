# Advanced Strategy Validation

Generated: 2026-08-18T07:49:56.667862+00:00
Validation verdict: **FAIL**

## Gate results

| Gate | Result |
|---|---|
| min_trades | PASS |
| min_win_rate | FAIL |
| min_profit_factor | FAIL |
| positive_expectancy | FAIL |
| max_drawdown_buffer | FAIL |
| stress_5bps_pf | FAIL |
| stress_10bps_pf | FAIL |
| walk_forward_stability | FAIL |
| cpcv_median_positive | FAIL |

## Baseline and cost stress

| Fee bps/side | Trades | Win rate | Profit factor | Expectancy | Max DD |
|---:|---:|---:|---:|---:|---:|
| 5 | 136 | 0.367647 | 0.68617 | -0.00088924 | -0.119751 |
| 10 | 136 | 0.345588 | 0.456627 | -0.00188924 | -0.230292 |
| 15 | 136 | 0.330882 | 0.301045 | -0.00288924 | -0.327717 |

The signal uses fixed rules and no fitted model. Walk-forward windows measure temporal stability; CPCV results are descriptive robustness checks, not proof of future profitability.
Paper trading and Telegram alerts are prohibited unless the validation verdict is PASS. This report does not authorize live execution.
