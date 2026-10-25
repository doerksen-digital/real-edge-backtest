"""Kline intervals supported by the data layer.

Only intervals that the Binance archive publishes as both monthly and daily files and that
have a fixed length are accepted. This matches DAILY_INTERVALS in the official downloader
(binance/binance-public-data, python/enums.py, MIT). 3d, 1w and 1mo are left out because
their candles are not aligned to a fixed multiple of the Unix epoch.
"""

INTERVAL_SECONDS: dict[str, int] = {
    "1s": 1,
    "1m": 60,
    "3m": 3 * 60,
    "5m": 5 * 60,
    "15m": 15 * 60,
    "30m": 30 * 60,
    "1h": 3600,
    "2h": 2 * 3600,
    "4h": 4 * 3600,
    "6h": 6 * 3600,
    "8h": 8 * 3600,
    "12h": 12 * 3600,
    "1d": 86400,
}


def interval_seconds(interval: str) -> int:
    """Return the interval length in seconds or raise ValueError for unsupported intervals."""
    try:
        return INTERVAL_SECONDS[interval]
    except KeyError:
        supported = ", ".join(INTERVAL_SECONDS)
        raise ValueError(f"unsupported interval {interval!r}, supported: {supported}") from None
