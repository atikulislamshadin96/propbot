def _f(v, default=0.0):
    """Safe float conversion — NaN/None হলে default"""
    try:
        if v is None:
            return default
        x = float(v)
        return x if x == x else default
    except Exception:
        return default
