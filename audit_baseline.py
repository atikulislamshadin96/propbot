"""Local-only repository audit; no network calls or trading actions."""
from importlib import import_module


def check_import(module_name: str) -> bool:
    try:
        import_module(module_name)
        print(f"PASS import {module_name}")
        return True
    except Exception as exc:
        print(f"FAIL import {module_name}: {type(exc).__name__}: {exc}")
        return False


def main() -> int:
    checks = [check_import(name) for name in ("config_v2", "datahub", "backtest_v2", "scan")]
    print(f"SUMMARY imports={sum(checks)}/{len(checks)}")
    return 0 if all(checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
