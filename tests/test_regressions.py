"""Deterministic regression tests for repaired PropBot behavior; no market calls."""
import unittest
from datetime import datetime, timezone
from tempfile import TemporaryDirectory
from unittest.mock import patch

import backtest_v2
import hl_funding
from purged_validation import purged_train_trades


class RiskCapTests(unittest.TestCase):
    def test_atr_stop_is_capped_by_max_risk(self):
        self.assertEqual(backtest_v2.capped_stop_distance(500, 10_000), 50.0)

    def test_atr_stop_stays_below_cap_when_already_smaller(self):
        self.assertEqual(backtest_v2.capped_stop_distance(10, 10_000), 15.0)


class PurgeTests(unittest.TestCase):
    def test_overlap_and_embargo_are_removed_from_training(self):
        trades = [
            {"open_bar": 2, "close_bar": 5},
            {"open_bar": 7, "close_bar": 9},
            {"open_bar": 10, "close_bar": 11},
        ]
        retained = purged_train_trades(trades, [(4, 6)], n_bars=20, embargo=2)
        self.assertEqual(retained, [trades[2]])


class FundingPaginationTests(unittest.TestCase):
    def test_string_timestamp_advances_cursor(self):
        now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)

        class Response:
            def raise_for_status(self):
                return None

            def json(self):
                return [{"time": str(now_ms), "fundingRate": "0.0001"}]

        with TemporaryDirectory() as temp_dir:
            original_cache = hl_funding.CACHE_DIR
            hl_funding.CACHE_DIR = temp_dir
            try:
                with patch.object(hl_funding.requests, "post", return_value=Response()):
                    result = hl_funding.fetch_hl_funding_history("BTC", days=1)
            finally:
                hl_funding.CACHE_DIR = original_cache
        self.assertEqual(len(result), 1)


if __name__ == "__main__":
    unittest.main()
