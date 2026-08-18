import unittest
from datetime import datetime, timezone

from signals_v3 import evaluate_divergence


class DivergenceSignalTests(unittest.TestCase):
    def base_extra(self):
        return {
            "coin": "BTC",
            "hl_funding": 0.00060,
            "dydx_funding": 0.00005,
            "spread": 0.00055,
            "spread_z": 3.0,
            "history_hours": 168,
        }

    def test_positive_spread_fades_hyperliquid_outlier(self):
        signal = evaluate_divergence({"timestamp": datetime.now(timezone.utc)}, self.base_extra())
        self.assertIsNotNone(signal)
        self.assertEqual(signal["side"], "SHORT_HL_LONG_DYDX")
        self.assertEqual(signal["receive_leg"], "SHORT Hyperliquid")
        self.assertEqual(signal["mode"], "PAPER_ONLY")

    def test_negative_spread_reverses_venue_legs(self):
        extra = self.base_extra()
        extra.update({"hl_funding": -0.00005, "dydx_funding": 0.00060, "spread": -0.00065, "spread_z": -3.0})
        signal = evaluate_divergence({}, extra)
        self.assertEqual(signal["side"], "LONG_HL_SHORT_DYDX")
        self.assertEqual(signal["receive_leg"], "SHORT dYdX")

    def test_missing_history_fails_closed(self):
        extra = self.base_extra()
        extra["history_hours"] = 10
        self.assertIsNone(evaluate_divergence({}, extra))

    def test_cost_gate_fails_closed(self):
        extra = self.base_extra()
        extra.update({"spread": 0.00001, "spread_z": 3.0})
        self.assertIsNone(evaluate_divergence({}, extra))


if __name__ == "__main__":
    unittest.main()
