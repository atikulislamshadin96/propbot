import numpy as np
import pandas as pd

def atr(df, period=14):
    h, l, c = df["high"], df["low"], df["close"]
    pc = c.shift(1)
    tr = np.maximum(h - l, np.maximum((h - pc).abs(), (l - pc).abs()))
    return tr.rolling(period).mean()

def rsi(df, period=14):
    d = df["close"].diff()
    gain = d.clip(lower=0).rolling(period).mean()
    loss = (-d.clip(upper=0)).rolling(period).mean()
    rs = gain / (loss + 1e-9)
    return 100 - 100 / (1 + rs)

def adx(df, period=14):
    h, l, c = df["high"], df["low"], df["close"]
    up, dn = h.diff(), -l.diff()
    plus_dm = pd.Series(np.where((up > dn) & (up > 0), up, 0.0), index=df.index)
    minus_dm = pd.Series(np.where((dn > up) & (dn > 0), dn, 0.0), index=df.index)
    tr = np.maximum(h - l, np.maximum((h - c.shift(1)).abs(), (l - c.shift(1)).abs()))
    atr_ = pd.Series(tr, index=df.index).rolling(period).mean()
    plus_di = 100 * plus_dm.rolling(period).mean() / (atr_ + 1e-9)
    minus_di = 100 * minus_dm.rolling(period).mean() / (atr_ + 1e-9)
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di + 1e-9)
    return dx.rolling(period).mean()

def compute_features(df):
    """সব indicator একসাথে — signals_v2-এর জন্য row তৈরি"""
    df = df.copy()
    df["atr"] = atr(df)
    df["rsi"] = rsi(df)
    df["ema20"] = df["close"].ewm(span=20, adjust=False).mean()
    df["ema50"] = df["close"].ewm(span=50, adjust=False).mean()
    df["adx"] = adx(df)

    # Realized vol percentile (480-bar rank)
    ret = np.log(df["close"] / df["close"].shift(1))
    rv = ret.rolling(96).std()
    df["rv_pct"] = rv.rolling(480, min_periods=96).rank(pct=True)

    # CVD (cumulative taker delta)
    df["taker_sell"] = df["volume"] - df["taker_buy"]
    df["cvd"] = (df["taker_buy"] - df["taker_sell"]).cumsum()
    df["px_12"] = df["close"].shift(12)
    df["cvd_12"] = df["cvd"].shift(12)
    df["taker"] = df["taker_buy"].rolling(20).sum() / (df["volume"].rolling(20).sum() + 1e-9)

    # Prior 12h (48-bar) levels + sweep detection
    df["prior_high"] = df["high"].rolling(48).max().shift(1)
    df["prior_low"] = df["low"].rolling(48).min().shift(1)
    df["sweep_sup"] = (df["low"] < df["prior_low"]) & (df["close"] > df["prior_low"])
    df["sweep_res"] = (df["high"] > df["prior_high"]) & (df["close"] < df["prior_high"])

    # Regime (ADX + EMA)
    df["regime"] = "RANGE"
    df.loc[(df["adx"] > 25) & (df["ema20"] > df["ema50"]), "regime"] = "TREND_UP"
    df.loc[(df["adx"] > 25) & (df["ema20"] < df["ema50"]), "regime"] = "TREND_DOWN"
    return df
