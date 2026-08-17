import pandas as pd
from bybit_data import bybit_funding_history
from okx_data import okx_funding_history

def _to_series(rows):
    df = pd.DataFrame(rows)
    if df.empty:
        return None
    df["dt"] = pd.to_datetime(df["ts"], unit="ms", utc=True)
    return df.set_index("dt")["rate"].resample("1h").last().ffill()

def funding_divergence_series(symbol="BTCUSDT"):
    try:
        by = _to_series(bybit_funding_history(symbol, 200))
        ok = _to_series(okx_funding_history())
        if by is None or ok is None:
            return None
        s = pd.concat([by.rename("by"), ok.rename("ok")], axis=1).ffill().dropna()
        s["div"] = s["by"] - s["ok"]
        w = s["div"].rolling(24 * 7, min_periods=24 * 3)
        s["div_z"] = (s["div"] - w.mean()) / (w.std() + 1e-9)
        return s
    except Exception:
        return None

def funding_divergence_current(symbol="BTCUSDT"):
    s = funding_divergence_series(symbol)
    if s is None or s.empty:
        return 0.0, 0.0
    last = s.iloc[-1]
    return float(last["div"]), float(last["div_z"])
