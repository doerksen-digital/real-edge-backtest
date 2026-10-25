"""Higher-timeframe candles built from a stored dataset, e.g. 4h from 1h.

Buckets are aligned to the Unix epoch, like Binance's own candles (4h candles open at 00:00,
04:00, ... UTC). Same rule as daily_candles: a bucket's OHLCV comes from the source candles
that exist in it, so a short outage leaves a candle built from the remaining hours, and a
bucket without any source candle is a gap, never filled. The last bucket is dropped if it is
incomplete only because the data ends.
"""

import pandas as pd

from real_edge_backtest.data.intervals import interval_seconds


def resample_candles(frame: pd.DataFrame, interval: str, timeframe: str) -> pd.DataFrame:
    """open_time, open, high, low, close, volume per `timeframe` bucket."""
    source = interval_seconds(interval)
    target = interval_seconds(timeframe)
    if target <= source or target % source:
        raise ValueError(
            f"timeframe {timeframe} must be a whole multiple of the data interval {interval}"
        )
    step = pd.Timedelta(seconds=target)
    epoch = pd.Timestamp(0, tz="UTC")
    bucket = epoch + ((frame["open_time"] - epoch) // step) * step
    grouped = frame.groupby(bucket, sort=True)
    out = pd.DataFrame(
        {
            "open": grouped["open"].first(),
            "high": grouped["high"].max(),
            "low": grouped["low"].min(),
            "close": grouped["close"].last(),
            "volume": grouped["volume"].sum(),
        }
    )
    out.index.name = "open_time"
    out = out.reset_index()
    last_source = frame["open_time"].iloc[-1]
    if last_source + pd.Timedelta(seconds=source) < out["open_time"].iloc[-1] + step:
        out = out.iloc[:-1]
    return out.reset_index(drop=True)
