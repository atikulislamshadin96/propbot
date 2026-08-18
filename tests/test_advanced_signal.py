import unittest

from advanced_signal import AdvancedSignalConfig, evaluate_forward, generate_signals


def rows(symbol, side=1, n=120):
    out = []
    price = 100.0
    for i in range(n):
        if i >= n - 1:
            move = 0.004 * side
            volume = 5000.0
            taker = 0.90 * volume if side > 0 else 0.10 * volume
            high = price * (1 + 0.006 * side if side > 0 else 0.002)
            low = price * (1 - 0.002 if side > 0 else 0.006)
            close = price * (1 + move)
        else:
            move = 0.0001 * ((i % 3) - 1)
            volume = 1000.0 + (i % 5) * 5
            taker = volume * (0.51 + 0.01 * ((i % 2) - 0.5))
            high, low = price * 1.001, price * 0.999
            close = price * (1 + move)
        out.append({"ts": i * 900000, "open": price, "high": high,
                    "low": low, "close": close, "volume": volume,
                    "taker_buy": taker})
        price = close
    return out


class AdvancedSignalTests(unittest.TestCase):
    def test_cross_asset_confirmation_and_levels(self):
        data = {"BTCUSDT": rows("BTCUSDT", 1), "ETHUSDT": rows("ETHUSDT", 1),
                "SOLUSDT": rows("SOLUSDT", 1)}
        cfg = AdvancedSignalConfig(min_quality_score=0.50)
        signals = generate_signals(data, cfg)
        self.assertEqual(len(signals), 3)
        for s in signals:
            self.assertEqual(s.side, "LONG")
            self.assertGreater(s.take_profit, s.entry)
            self.assertLess(s.stop_loss, s.entry)
            self.assertGreaterEqual(s.reward_risk, 1.5)
            self.assertEqual(s.mode, "paper")

    def test_no_confirmation_means_no_signal(self):
        data = {"BTCUSDT": rows("BTCUSDT", 1), "ETHUSDT": rows("ETHUSDT", -1),
                "SOLUSDT": rows("SOLUSDT", -1)}
        cfg = AdvancedSignalConfig(min_quality_score=0.50, breadth_min=0.67)
        self.assertEqual(generate_signals(data, cfg), [])

    def test_max_three_signals(self):
        data = {f"SYM{i}USDT": rows(f"SYM{i}USDT", 1) for i in range(5)}
        cfg = AdvancedSignalConfig(min_quality_score=0.50)
        self.assertLessEqual(len(generate_signals(data, cfg)), 3)

    def test_forward_evaluation_uses_future_rows(self):
        data = {"BTCUSDT": rows("BTCUSDT", 1), "ETHUSDT": rows("ETHUSDT", 1),
                "SOLUSDT": rows("SOLUSDT", 1)}
        signal = generate_signals(data, AdvancedSignalConfig(min_quality_score=0.50))[0]
        future = [{"high": signal.take_profit * 1.01, "low": signal.entry,
                   "close": signal.take_profit}]
        result = evaluate_forward(signal, future, fee_bps=5.0)
        self.assertTrue(result["valid"])
        self.assertEqual(result["reason"], "target")
        self.assertLess(result["net_return"], result["gross_return"])


if __name__ == "__main__":
    unittest.main()
