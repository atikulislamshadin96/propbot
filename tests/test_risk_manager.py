import unittest
from datetime import datetime, timedelta, timezone

from risk_manager import assess_candidate, consecutive_losses, max_drawdown_pct


class RiskManagerTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 8, 18, 12, 0, tzinfo=timezone.utc)
        self.candidate = {"mode": "PAPER_ONLY", "symbol": "BTCUSDT", "risk_pct": 0.5}

    def test_allows_clean_candidate(self):
        result = assess_candidate(self.candidate, open_trades=[], closed_trades=[], all_trades=[], now=self.now)
        self.assertTrue(result["allowed"])
        self.assertEqual(result["reasons"], [])

    def test_rejects_duplicate_symbol_and_portfolio_cap(self):
        open_trades = [
            {"symbol": "BTCUSDT", "risk_pct": 0.5},
            {"symbol": "ETHUSDT", "risk_pct": 0.5},
        ]
        result = assess_candidate(self.candidate, open_trades=open_trades, closed_trades=[], now=self.now)
        self.assertFalse(result["allowed"])
        self.assertIn("max_positions", result["reasons"])
        self.assertIn("duplicate_symbol", result["reasons"])
        self.assertIn("portfolio_risk_cap", result["reasons"])

    def test_rejects_daily_loss_and_consecutive_losses(self):
        closed = [
            {"closed_ts": "2026-08-18T09:00:00+00:00", "pnl_pct": -2.0},
            {"closed_ts": "2026-08-18T10:00:00+00:00", "pnl_pct": -2.0},
            {"closed_ts": "2026-08-18T11:00:00+00:00", "pnl_pct": -2.0},
        ]
        result = assess_candidate(self.candidate, open_trades=[], closed_trades=closed, now=self.now)
        self.assertFalse(result["allowed"])
        self.assertIn("daily_loss_circuit_breaker", result["reasons"])
        self.assertIn("consecutive_loss_circuit_breaker", result["reasons"])
        self.assertEqual(consecutive_losses(closed), 3)

    def test_rejects_drawdown_and_cooldown(self):
        closed = [
            {"closed_ts": "2026-08-17T10:00:00+00:00", "pnl_pct": -5.0},
            {"closed_ts": "2026-08-18T11:45:00+00:00", "pnl_pct": -5.0},
        ]
        result = assess_candidate(self.candidate, open_trades=[], closed_trades=closed, now=self.now)
        self.assertFalse(result["allowed"])
        self.assertIn("total_drawdown_circuit_breaker", result["reasons"])
        self.assertIn("cooldown", result["reasons"])
        self.assertLessEqual(max_drawdown_pct(closed), -9.0)

    def test_rejects_too_many_opened_today(self):
        all_trades = [
            {"ts": f"2026-08-18T0{i}:00:00+00:00", "symbol": f"COIN{i}"} for i in range(3)
        ]
        result = assess_candidate(self.candidate, open_trades=[], closed_trades=[], all_trades=all_trades, now=self.now)
        self.assertFalse(result["allowed"])
        self.assertIn("max_trades_day", result["reasons"])


if __name__ == "__main__":
    unittest.main()
