import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import advanced_scan


class AdvancedScanGateTests(unittest.TestCase):
    def test_validation_gate_blocks_telegram_and_paper(self):
        with tempfile.TemporaryDirectory() as td:
            report = Path(td) / "validation.json"
            scan_report = Path(td) / "scan.json"
            ledger = Path(td) / "paper.jsonl"
            report.write_text(json.dumps({"validation_pass": False}))
            with patch.object(advanced_scan, "REPORT", report), \
                 patch.object(advanced_scan, "SCAN_REPORT", scan_report), \
                 patch.object(advanced_scan, "PAPER_LEDGER", ledger), \
                 patch.object(advanced_scan, "klines", return_value=[]), \
                 patch.dict(os.environ, {"ENABLE_ADVANCED_PAPER": "1", "ENABLE_ADVANCED_TELEGRAM": "1"}, clear=False):
                result = advanced_scan.run()
            self.assertEqual(result["deployment_status"], "BLOCKED_VALIDATION_FAIL")
            self.assertEqual(result["paper_recorded"], [])
            self.assertEqual(result["telegram_alerts_sent"], 0)
            self.assertFalse(ledger.exists())


if __name__ == "__main__":
    unittest.main()
