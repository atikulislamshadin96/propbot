import unittest

import numpy as np
import pandas as pd

from signals_v3 import evaluate_divergence
from threshold_validation import add_adaptive_thresholds, count_triggers


class ThresholdValidationTests(unittest.TestCase):
    def test_relaxed_profile_is_explicitly_research_only(self):
        extra = {
            "coin": "BTC",
            "hl_funding": 0.00020,
            "dydx_funding": 0.00000,
            "spread": 0.00020,
            "spread_z": 2.0,
            "history_hours": 168,
            "adaptive_z_threshold": 1.5,
            "adaptive_bps_threshold": 15.0,
        }
        strict = evaluate_divergence({}, extra)
        relaxed = evaluate_divergence({}, extra, profile="research_relaxed")
        self.assertIsNone(strict)
        self.assertIsNotNone(relaxed)
        self.assertEqual(relaxed["mode"], "RESEARCH_ONLY_RELAXED")

    def test_non_overlapping_entries_apply_cooldown(self):
        index = pd.date_range("2026-01-01", periods=10, freq="h", tz="UTC")
        scored = pd.DataFrame(
            {
                "spread_z": [2.0] * 10,
                "expected_gross_bps": [20.0] * 10,
            },
            index=index,
        )
        result = count_triggers(scored, 1.5, 15.0, economic_only=False)
        self.assertEqual(result["raw_triggers"], 10)
        self.assertEqual(result["non_overlapping_entries"], 2)

    def test_adaptive_thresholds_do_not_use_future_observations(self):
        index = pd.date_range("2026-01-01", periods=300, freq="h", tz="UTC")
        base = pd.DataFrame(
            {
                "spread": np.sin(np.arange(len(index)) / 5.0) * 0.00001,
                "spread_z": np.ones(len(index)) * 2.0,
            },
            index=index,
        )
        base["history_hours"] = 168
        altered = base.copy()
        altered.iloc[-1, altered.columns.get_loc("spread")] = 0.25
        first = add_adaptive_thresholds(base)
        second = add_adaptive_thresholds(altered)
        prefix = first.index[:-1]
        pd.testing.assert_series_equal(
            first.loc[prefix, "adaptive_z_threshold"],
            second.loc[prefix, "adaptive_z_threshold"],
            check_names=False,
        )


if __name__ == "__main__":
    unittest.main()
