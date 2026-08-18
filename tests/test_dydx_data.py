import unittest
from unittest.mock import Mock, patch

import dydx_data


class DydxDataTests(unittest.TestCase):
    @patch("dydx_data.requests.get")
    def test_current_funding_parses_public_market_payload(self, get):
        response = Mock()
        response.json.return_value = {
            "markets": {
                "BTC-USD": {
                    "status": "ACTIVE",
                    "nextFundingRate": "0.0001",
                    "oraclePrice": "64000",
                    "openInterest": "100",
                }
            }
        }
        response.raise_for_status.return_value = None
        get.return_value = response
        snapshot = dydx_data.fetch_current_funding("btc")
        self.assertEqual(snapshot["ticker"], "BTC-USD")
        self.assertAlmostEqual(snapshot["funding"], 0.0001)
        get.assert_called_once_with("https://indexer.dydx.trade/v4/perpetualMarkets", timeout=20)

    @patch("dydx_data.requests.get")
    def test_missing_market_fails_closed(self, get):
        response = Mock()
        response.json.return_value = {"markets": {}}
        response.raise_for_status.return_value = None
        get.return_value = response
        with self.assertRaises(ValueError):
            dydx_data.fetch_current_funding("btc")


if __name__ == "__main__":
    unittest.main()
