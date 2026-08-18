"""Network-free behavioral checks for documented PropBot defects."""
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import datahub
import hl_funding
import scan


def run_check(name, check):
    try:
        check()
        print(f"PASS {name}")
        return True
    except Exception as exc:
        print(f"FAIL {name}: {type(exc).__name__}: {exc}")
        return False


def check_datahub_normalization():
    series = datahub._to_series([{"ts": 1_700_000_000_000, "rate": 0.0001}])
    assert len(series) == 1


def check_live_feature_parity():
    assert "requests" in scan.__dict__, "scan.py uses requests without importing it"
    source = Path("scan.py").read_text()
    assert '"hl_funding_z"' in source, "live extra payload omits hl_funding_z"


def check_risk_cap_semantics():
    from backtest_v2 import capped_stop_distance

    capped = capped_stop_distance(atr_value=500.0, entry_price=10_000.0)
    assert capped == 50.0, "stop distance must not exceed the 0.50% risk cap"


def check_purged_validation_semantics():
    from purged_validation import purged_train_trades

    trades = [
        {"open_bar": 2, "close_bar": 5},
        {"open_bar": 7, "close_bar": 9},
        {"open_bar": 10, "close_bar": 11},
    ]
    retained = purged_train_trades(trades, test=[(4, 6)], n_bars=20, embargo=2)
    assert retained == [trades[2]], "overlap and embargo labels must be removed from training"


class _Response:
    def __init__(self, rows):
        self.rows = rows

    def raise_for_status(self):
        return None

    def json(self):
        return self.rows


def check_hl_string_timestamp_handling():
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    with TemporaryDirectory() as temp_dir:
        original_cache = hl_funding.CACHE_DIR
        hl_funding.CACHE_DIR = temp_dir
        try:
            with patch.object(
                hl_funding.requests,
                "post",
                return_value=_Response([{"time": str(now_ms), "fundingRate": "0.0001"}]),
            ):
                output = hl_funding.fetch_hl_funding_history("BTC", days=1)
            assert len(output) == 1, "string timestamps should not stop pagination"
        finally:
            hl_funding.CACHE_DIR = original_cache


def main():
    checks = [
        run_check("datahub normalization", check_datahub_normalization),
        run_check("risk-cap semantics", check_risk_cap_semantics),
        run_check("live feature parity", check_live_feature_parity),
        run_check("purged-validation semantics", check_purged_validation_semantics),
        run_check("Hyperliquid pagination timestamp", check_hl_string_timestamp_handling),
    ]
    print(f"SUMMARY behavior={sum(checks)}/{len(checks)}")
    return 0 if all(checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
