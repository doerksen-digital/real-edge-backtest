"""Synthetic candle helpers for engine tests."""

import numpy as np
import pandas as pd


def make_candles(
    opens, highs, lows, closes, volumes=None, start: str = "2026-01-01T00:00:00Z"
) -> pd.DataFrame:
    n = len(closes)
    return pd.DataFrame(
        {
            "open_time": pd.date_range(start, periods=n, freq="h"),
            "open": np.asarray(opens, dtype=float),
            "high": np.asarray(highs, dtype=float),
            "low": np.asarray(lows, dtype=float),
            "close": np.asarray(closes, dtype=float),
            "volume": np.ones(n) if volumes is None else np.asarray(volumes, dtype=float),
        }
    )


def random_walk(n: int, seed: int, start: str = "2025-01-01T00:00:00Z") -> pd.DataFrame:
    """Hourly candles on the 0.01 tick grid with a mild random walk."""
    rng = np.random.default_rng(seed)
    closes = np.round(30000 + np.cumsum(rng.normal(0, 60, n)), 2)
    opens = np.round(np.concatenate(([closes[0]], closes[:-1])), 2)
    spread = np.round(np.abs(rng.normal(0, 40, n)), 2)
    highs = np.maximum(opens, closes) + spread
    lows = np.minimum(opens, closes) - np.round(np.abs(rng.normal(0, 40, n)), 2)
    volumes = np.round(rng.uniform(10, 100, n), 5)
    return make_candles(opens, highs, lows, closes, volumes, start=start)
