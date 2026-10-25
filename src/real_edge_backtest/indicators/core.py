"""Core indicators, each matching the Pine Script v6 reference manual definition.

All functions take and return numpy float arrays. na is NaN. Every value at index i depends
only on inputs at indices <= i, so no indicator can look ahead.

Reference (tradingview.com/pine-script-reference/v6):
- ta.ema: alpha = 2 / (length + 1), seeded with the first source value
- ta.rma: alpha = 1 / length, seeded with ta.sma(source, length)
- ta.atr: ta.rma of true range; the first bar's true range is high - low
- math.sum: sliding sum of the last `length` values, na until `length` values exist
- ta.crossover(a, b): a > b and a[1] <= b[1]; ta.crossunder(a, b): a < b and a[1] >= b[1]
- math.round: nearest integer, ties rounding up
"""

import math

import numpy as np


def pine_round(value: float) -> int:
    """math.round(): nearest integer, ties rounding up (unlike Python's banker's rounding)."""
    return math.floor(value + 0.5)


def hlc3(high: np.ndarray, low: np.ndarray, close: np.ndarray) -> np.ndarray:
    return (high + low + close) / 3


def ema(source: np.ndarray, length: int) -> np.ndarray:
    """ta.ema. na source values are skipped and the last value is carried."""
    alpha = 2 / (length + 1)
    out = np.full(len(source), np.nan)
    value = np.nan
    for i, x in enumerate(source):
        if not np.isnan(x):
            value = x if np.isnan(value) else alpha * x + (1 - alpha) * value
        out[i] = value
    return out


def sma(source: np.ndarray, length: int) -> np.ndarray:
    """ta.sma over the last `length` non-na values."""
    out = np.full(len(source), np.nan)
    window: list[float] = []
    for i, x in enumerate(source):
        if not np.isnan(x):
            window.append(x)
            if len(window) > length:
                window.pop(0)
        if len(window) == length:
            out[i] = sum(window) / length
    return out


def rma(source: np.ndarray, length: int) -> np.ndarray:
    """ta.rma: seeded with the SMA of the first `length` non-na values."""
    alpha = 1 / length
    out = np.full(len(source), np.nan)
    seed = sma(source, length)
    value = np.nan
    for i, x in enumerate(source):
        if np.isnan(value):
            value = seed[i]
        elif not np.isnan(x):
            value = alpha * x + (1 - alpha) * value
        out[i] = value
    return out


def true_range(high: np.ndarray, low: np.ndarray, close: np.ndarray) -> np.ndarray:
    prev_close = np.concatenate(([np.nan], close[:-1]))
    tr = np.maximum(high - low, np.maximum(np.abs(high - prev_close), np.abs(low - prev_close)))
    tr[0] = high[0] - low[0]
    return tr


def atr(high: np.ndarray, low: np.ndarray, close: np.ndarray, length: int) -> np.ndarray:
    return rma(true_range(high, low, close), length)


def rolling_sum(source: np.ndarray, length: int) -> np.ndarray:
    """math.sum: each window is summed on its own, so no error accumulates over the series.

    Unlike Pine, a na value inside a window makes that window na. Candle data has no na values.
    """
    out = np.full(len(source), np.nan)
    if len(source) >= length:
        windows = np.lib.stride_tricks.sliding_window_view(source, length)
        out[length - 1 :] = windows.sum(axis=1)
    return out


def rolling_vwap(
    high: np.ndarray, low: np.ndarray, close: np.ndarray, volume: np.ndarray, length: int
) -> np.ndarray:
    """sum(hlc3 * volume, length) / sum(volume, length), na where the volume sum is 0."""
    pv = rolling_sum(hlc3(high, low, close) * volume, length)
    v = rolling_sum(volume, length)
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(v > 0, pv / v, np.nan)


def _previous(values: np.ndarray) -> np.ndarray:
    return np.concatenate(([np.nan], values[:-1]))


def crossover(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    with np.errstate(invalid="ignore"):
        return (a > b) & (_previous(a) <= _previous(b))


def crossunder(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    with np.errstate(invalid="ignore"):
        return (a < b) & (_previous(a) >= _previous(b))
