import unittest

from regime_filter import classify_regime, filter_candidates, strategy_allowed


class RegimeFilterTests(unittest.TestCase):
    def base(self):
        return {"adx": 30.0, "ema20": 102.0, "ema50": 100.0, "rv_pct": 0.5, "dvol_pct": 0.5}

    def test_uptrend_is_open_for_long_trend(self):
        regime = classify_regime(self.base())
        self.assertEqual(regime["regime"], "TREND_UP")
        allowed, reason = strategy_allowed("trend_following", {"side": "BUY"}, regime)
        self.assertTrue(allowed)
        self.assertEqual(reason, "allowed")

    def test_range_allows_mean_reversion(self):
        row = {"adx": 15.0, "ema20": 100.0, "ema50": 100.0, "rv_pct": 0.4, "dvol_pct": 0.5}
        regime = classify_regime(row)
        self.assertEqual(regime["regime"], "RANGE")
        allowed, _ = strategy_allowed("mean_reversion", {"side": "BUY"}, regime)
        self.assertTrue(allowed)

    def test_extreme_volatility_blocks_candidates(self):
        row = {**self.base(), "rv_pct": 0.99}
        result = filter_candidates([{"strategy_id": "trend_following", "side": "BUY"}], row)
        self.assertEqual(result["risk_state"], "BLOCKED")
        self.assertEqual(result["action"], "HOLD")
        self.assertEqual(result["rejected"][0]["regime_reason"], "risk_off_or_unknown")

    def test_missing_inputs_fail_closed(self):
        regime = classify_regime({"adx": 20.0})
        self.assertEqual(regime["regime"], "UNKNOWN")
        self.assertEqual(regime["risk_state"], "BLOCKED")


if __name__ == "__main__":
    unittest.main()
