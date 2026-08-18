import unittest

from strategy_portfolio import (
    evaluate_portfolio,
    mean_reversion_candidate,
    trend_following_candidate,
)


class StrategyPortfolioTests(unittest.TestCase):
    def base_row(self):
        return {
            "symbol": "BTCUSDT",
            "timestamp": "2026-08-18T00:00:00+00:00",
            "close": 102.0,
            "atr": 1.0,
            "vol_ratio": 1.0,
            "rv_pct": 0.5,
            "dvol_pct": 0.5,
        }

    def test_trend_following_long(self):
        row = {
            **self.base_row(),
            "ema20": 101.0,
            "ema50": 99.0,
            "adx": 30.0,
            "rsi": 60.0,
        }
        candidate = trend_following_candidate(row)
        self.assertIsNotNone(candidate)
        self.assertEqual(candidate["strategy_id"], "trend_following")
        self.assertEqual(candidate["side"], "BUY")

    def test_mean_reversion_short_in_range(self):
        row = {
            **self.base_row(),
            "adx": 18.0,
            "rsi": 72.0,
            "bb_z": 2.4,
        }
        candidate = mean_reversion_candidate(row)
        self.assertIsNotNone(candidate)
        self.assertEqual(candidate["strategy_id"], "mean_reversion")
        self.assertEqual(candidate["side"], "SELL")

    def test_mean_reversion_is_vetoed_in_strong_trend(self):
        row = {**self.base_row(), "adx": 30.0, "rsi": 28.0, "bb_z": -2.4}
        self.assertIsNone(mean_reversion_candidate(row))

    def test_portfolio_keeps_hedged_funding_separate_from_directional_exposure(self):
        candle = {
            **self.base_row(),
            "ema20": 101.0,
            "ema50": 99.0,
            "adx": 30.0,
            "rsi": 60.0,
            "bb_z": 0.0,
        }
        funding = {
            "timestamp": "2026-08-18T00:00:00+00:00",
            "hl_funding": -0.00010,
            "dydx_funding": 0.00050,
            "spread": -0.00060,
            "spread_z": -3.0,
            "history_hours": 168,
        }
        result = evaluate_portfolio(candle, funding)
        self.assertFalse(result["direction_conflict"])
        self.assertEqual(result["portfolio_action"], "REVIEW_PAPER_CANDIDATES")
        self.assertEqual(result["candidate_count"], 2)


if __name__ == "__main__":
    unittest.main()
