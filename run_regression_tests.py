"""Run repository regression tests without invoking market-data clients or trade execution."""
import sys
import unittest


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.discover("tests")
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    raise SystemExit(0 if result.wasSuccessful() else 1)
