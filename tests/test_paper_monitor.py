import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import paper_monitor


class PaperMonitorTests(unittest.TestCase):
    def test_execution_quality_uses_recorded_timestamps(self):
        now = datetime.now(timezone.utc)
        trades = [
            {
                "status": "tp",
                "ts": (now - timedelta(minutes=20)).isoformat(),
                "signal_ts": (now - timedelta(minutes=21)).isoformat(),
                "closed_ts": (now - timedelta(minutes=5)).isoformat(),
                "pnl_pct": 1.0,
            }
        ]
        quality = paper_monitor.execution_quality(trades)
        self.assertEqual(quality["paper_trades_observed"], 1)
        self.assertEqual(quality["closed_trades_observed"], 1)
        self.assertEqual(quality["median_signal_to_paper_open_minutes"], 1.0)
        self.assertEqual(quality["median_paper_holding_minutes"], 15.0)
        self.assertIsNone(quality["observed_exchange_slippage_bps"])
        self.assertEqual(quality["fill_quality_status"], "UNOBSERVED_PAPER_PROXY_ONLY")

    def test_run_is_read_only_and_writes_reports(self):
        with tempfile.TemporaryDirectory() as directory:
            json_path = Path(directory) / "monitor.json"
            md_path = Path(directory) / "monitor.md"
            with patch.object(paper_monitor, "JSON_PATH", json_path), \
                 patch.object(paper_monitor, "MD_PATH", md_path), \
                 patch.object(paper_monitor, "data_health", return_value=[{"symbol": "BTCUSDT", "status": "FRESH", "age_minutes": 2.0, "error": None}]), \
                 patch.object(paper_monitor.db, "closed_trades", return_value=[]), \
                 patch.object(paper_monitor.db, "open_trades", return_value=[]), \
                 patch.object(paper_monitor.db, "all_trades", return_value=[]), \
                 patch.object(paper_monitor.db, "daily_pnl_pct", return_value=0.0):
                report = paper_monitor.run(["BTCUSDT"])
            self.assertEqual(report["mode"], "PAPER_ONLY_READ_ONLY")
            self.assertTrue(json_path.exists())
            self.assertTrue(md_path.exists())
            self.assertIn("read-only", md_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
