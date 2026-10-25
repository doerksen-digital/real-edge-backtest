"""Daily candles built from intraday candles, and a lookahead-free "previous completed day" lookup.

TradingView's daily bar for BINANCE:BTCUSDT opens at 00:00 UTC (checked on TradingView with
request.security(syminfo.tickerid, "D", time, lookahead_on)), so days are UTC calendar days.

request.security("D", expr[1], lookahead = barmerge.lookahead_on) returns, on every intraday bar
of day D, the value of expr on the daily bar before D. previous_day_values() reproduces that.
"""

import numpy as np
import pandas as pd


def daily_candles(frame: pd.DataFrame) -> pd.DataFrame:
    """OHLCV per UTC day from candles with a UTC open_time column. Days without candles are
    absent, like on TradingView."""
    day = frame["open_time"].dt.floor("D")
    grouped = frame.groupby(day, sort=True)
    return pd.DataFrame(
        {
            "open": grouped["open"].first(),
            "high": grouped["high"].max(),
            "low": grouped["low"].min(),
            "close": grouped["close"].last(),
            "volume": grouped["volume"].sum(),
        }
    )


def previous_day_values(
    open_time: pd.Series, daily_index: pd.DatetimeIndex, daily_values: np.ndarray
) -> np.ndarray:
    """For each intraday bar, the daily value of the previous daily bar (expr[1] on day D)."""
    shifted = pd.Series(daily_values, index=daily_index).shift(1)
    return shifted.reindex(open_time.dt.floor("D")).to_numpy(dtype=float)
