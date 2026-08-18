"""Funding-divergence research tests with synthetic fixtures only; no live endpoints or orders."""
import unittest

import pandas as pd

import config_v2 as cfg
from funding_data import dydx_ticker
from funding_event_study import run_event_study, summarize
from funding_strategy import divergence_panel, paper_candidate


def panel_with_extreme(last_spread=0.0005):
    index = pd.date_range("2026-01-01", periods=200, freq="h", tz="UTC")
    panel = pd.DataFrame({"hl_funding": 0.0, "dydx_funding": 0.0}, index=index)
    panel.iloc[-1, panel.columns.get_loc("hl_funding")] = last_spread
    return panel


class FundingAdapterTests(unittest.TestCase):
    def test_dydx_ticker_mapping(self):
        self.assertEqual(dydx_ticker("btc"), "BTC-USD")

    def test_bad_ticker_is_rejected(self):
        with self.assertRaises(ValueError):
            dydx_ticker("BTC-USDT")


class FundingSignalTests(unittest.TestCase):
    def test_extreme_positive_spread_selects_short_hyperliquid_receive_leg(self):
        candidate = paper_candidate(panel_with_extreme())
        self.assertIsNotNone(candidate)
        self.assertEqual(candidate["receive_leg"], "SHORT Hyperliquid")
        self.assertEqual(candidate["pay_leg"], "LONG dYdX")
        self.assertEqual(candidate["mode"], "PAPER_ONLY")

    def test_insufficient_history_fails_closed(self):
        short_panel = panel_with_extreme().iloc[: cfg.FUNDING_MIN_HISTORY_HOURS - 1]
        self.assertTrue(divergence_panel(short_panel).empty)
        self.assertIsNone(paper_candidate(short_panel))

    def test_cost_gate_suppresses_unprofitable_spread(self):
        candidate = paper_candidate(panel_with_extreme(last_spread=0.00001))
        self.assertIsNone(candidate)

    def test_event_study_uses_only_forward_funding_observations(self):
        panel = panel_with_extreme()
        panel.iloc[-9:, panel.columns.get_loc("hl_funding")] = 0.0005
        events = run_event_study(panel)
        self.assertGreaterEqual(len(events), 1)
        self.assertTrue((events["funding_hours_observed"] == cfg.FUNDING_EXPECTED_HOLD_HOURS).all())
        self.assertEqual(summarize(events)["events"], len(events))


if __name__ == "__main__":
    unittest.main()
