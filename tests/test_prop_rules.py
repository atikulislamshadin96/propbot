import unittest

from prop_rules import PropRules, evaluate


class PropRulesTests(unittest.TestCase):
    def test_clean_paper_snapshot_is_active(self):
        decision = evaluate({
            "equity": 100500.0,
            "day_start_equity": 100000.0,
            "peak_equity": 100500.0,
            "open_risk_pct": 0.5,
            "trades_today": 1,
            "consecutive_losses": 0,
            "max_data_age_minutes": 5.0,
            "data_ok": True,
        }, PropRules())
        self.assertEqual(decision["status"], "ACTIVE_PAPER")
        self.assertTrue(decision["allowed_for_paper"])
        self.assertFalse(decision["kill_switch"])

    def test_daily_loss_and_stale_data_block(self):
        decision = evaluate({
            "equity": 94000.0,
            "day_start_equity": 100000.0,
            "peak_equity": 100000.0,
            "open_risk_pct": 0.0,
            "trades_today": 0,
            "consecutive_losses": 0,
            "max_data_age_minutes": 45.0,
            "data_ok": False,
        }, PropRules())
        self.assertEqual(decision["status"], "BLOCKED")
        self.assertTrue(decision["kill_switch"])
        self.assertIn("daily_loss_limit_breached", decision["reasons"])
        self.assertIn("data_freshness_failed", decision["reasons"])

    def test_target_is_not_live_authorization(self):
        decision = evaluate({
            "equity": 110000.0,
            "day_start_equity": 110000.0,
            "peak_equity": 110000.0,
            "open_risk_pct": 0.0,
            "trades_today": 0,
            "consecutive_losses": 0,
            "max_data_age_minutes": 1.0,
            "data_ok": True,
        }, PropRules())
        self.assertEqual(decision["status"], "TARGET_REACHED")
        self.assertTrue(decision["target_reached"])
        self.assertEqual(decision["mode"], "PAPER_ONLY")


if __name__ == "__main__":
    unittest.main()
