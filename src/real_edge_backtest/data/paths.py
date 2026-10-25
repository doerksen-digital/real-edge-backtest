"""Local and remote locations of spot kline files."""

from pathlib import Path

BASE_URL = "https://data.binance.vision/"


def archive_dir(period: str, symbol: str, interval: str) -> str:
    """Archive folder of a symbol and interval, relative to BASE_URL.

    Same layout as get_path() in the official downloader
    (binance/binance-public-data, python/utility.py, MIT).
    """
    return f"data/spot/{period}/klines/{symbol}/{interval}/"


def file_name(symbol: str, interval: str, label: str) -> str:
    """Zip name, where label is YYYY-MM for monthly and YYYY-MM-DD for daily files."""
    return f"{symbol}-{interval}-{label}.zip"


def raw_dir(data_dir: Path, period: str, symbol: str, interval: str) -> Path:
    """Local mirror of the archive folder for verified zips and their checksum files."""
    return data_dir / "raw" / "spot" / period / "klines" / symbol / interval


def parquet_path(data_dir: Path, symbol: str, interval: str) -> Path:
    """The cleaned dataset of one symbol and interval."""
    return data_dir / "spot" / "klines" / symbol / f"{interval}.parquet"
