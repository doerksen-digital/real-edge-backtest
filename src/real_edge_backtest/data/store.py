"""Turn verified kline zips into one cleaned Parquet dataset per symbol and interval.

Column layout follows the spot klines table in the binance/binance-public-data README.
Spot timestamps are milliseconds before 2025-01-01 and microseconds from then on. The unit is
detected per row from the value size, so a file that breaks that rule is still read correctly
or rejected, never silently misread. The detected unit is kept in the time_unit column because
close_time is open_time + interval - 1 unit of the source file.

Cleaning rules (raw zips are never changed, gaps are never filled):
- exact duplicate rows are dropped; the same open_time with different values is an error
- candles whose open_time is off the interval grid are excluded and become part of a gap
  (BTCUSDT 1h, 2018-02-09 to 2018-02-11: 43 candles shifted by 28m14.789s after an outage)
- a candle that closes early (the last one before an outage) is kept and marked partial=True
  if it has trades; a partial candle with zero trades is a placeholder and is excluded
"""

import io
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from real_edge_backtest.data.download import verify_local
from real_edge_backtest.data.intervals import interval_seconds
from real_edge_backtest.data.paths import parquet_path, raw_dir

RAW_COLUMNS = [
    "open_time",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "close_time",
    "quote_volume",
    "trades",
    "taker_buy_base_volume",
    "taker_buy_quote_volume",
    "ignore",
]
FLOAT_COLUMNS = [
    "open",
    "high",
    "low",
    "close",
    "volume",
    "quote_volume",
    "taker_buy_base_volume",
    "taker_buy_quote_volume",
]

# Microsecond values for any date after 2001 are above 1e15, millisecond values below.
MICROSECOND_MIN = 10**15
MILLISECOND_MIN = 10**12


class DataError(RuntimeError):
    """The raw data cannot be turned into a clean dataset."""


@dataclass
class BuildResult:
    path: Path
    files_used: int
    rows: int
    exact_duplicates_dropped: int
    off_grid: list[pd.Timestamp] = field(default_factory=list)
    placeholders: list[pd.Timestamp] = field(default_factory=list)


def is_aligned(open_time: pd.Series, step: pd.Timedelta) -> pd.Series:
    """True where the open time is an exact multiple of the interval since the Unix epoch."""
    return ((open_time - pd.Timestamp(0, tz="UTC")) % step) == pd.Timedelta(0)


def full_length(frame: pd.DataFrame, step: pd.Timedelta) -> pd.Series:
    """Expected close_time - open_time of a complete candle: interval minus one source unit,
    1 ms for millisecond-era rows and 1 us for microsecond-era rows."""
    last_unit = {"ms": pd.Timedelta(milliseconds=1), "us": pd.Timedelta(microseconds=1)}
    return step - frame["time_unit"].map(last_unit)


def _to_utc(values: pd.Series, units: pd.Series) -> pd.Series:
    micros = values.where(units == "us", values * 1000)
    return pd.to_datetime(micros, unit="us", utc=True)


def _units(values: pd.Series) -> pd.Series:
    return pd.Series("ms", index=values.index).where(values < MICROSECOND_MIN, "us")


def read_zip(zip_path: Path) -> pd.DataFrame:
    """Read one kline zip into a DataFrame with UTC timestamps."""
    with zipfile.ZipFile(zip_path) as archive:
        names = [n for n in archive.namelist() if n.endswith(".csv")]
        if len(names) != 1:
            raise DataError(f"{zip_path.name}: expected one CSV, found {names}")
        raw = archive.read(names[0])

    first_field = raw.split(b"\n", 1)[0].split(b",", 1)[0].strip()
    has_header = not first_field.isdigit()
    frame = pd.read_csv(
        io.BytesIO(raw),
        header=None,
        names=RAW_COLUMNS,
        skiprows=1 if has_header else 0,
        dtype={"open_time": "int64", "close_time": "int64", "trades": "int64"}
        | dict.fromkeys(FLOAT_COLUMNS, "float64"),
        usecols=RAW_COLUMNS[:-1],
    )

    open_raw = frame["open_time"]
    units = _units(open_raw)
    bad = open_raw < MILLISECOND_MIN
    if bad.any():
        raise DataError(f"{zip_path.name}: unknown timestamp unit, e.g. {open_raw[bad].iloc[0]}")
    if (units != _units(frame["close_time"])).any():
        raise DataError(f"{zip_path.name}: open_time and close_time use different units")

    frame["open_time"] = _to_utc(open_raw, units)
    frame["close_time"] = _to_utc(frame["close_time"], units)
    frame["time_unit"] = units
    return frame


def _select_files(data_dir: Path, symbol: str, interval: str) -> list[Path]:
    """Monthly zips, plus daily zips for months that have no monthly zip."""
    prefix = len(f"{symbol}-{interval}-")
    monthly = sorted(raw_dir(data_dir, "monthly", symbol, interval).glob("*.zip"))
    covered = {p.stem[prefix:] for p in monthly}
    daily = [
        p
        for p in sorted(raw_dir(data_dir, "daily", symbol, interval).glob("*.zip"))
        if p.stem[prefix:][:7] not in covered
    ]
    return monthly + daily


def build_dataset(data_dir: Path, symbol: str, interval: str) -> BuildResult:
    """Rebuild the Parquet dataset from all verified zips."""
    symbol = symbol.upper()
    files = _select_files(data_dir, symbol, interval)
    if not files:
        raise DataError(f"no downloaded files for {symbol} {interval} under {data_dir}")
    unverified = [p.name for p in files if not verify_local(p)]
    if unverified:
        raise DataError(f"files failed SHA-256 check, run download again: {unverified}")

    frame = pd.concat([read_zip(p) for p in files], ignore_index=True)
    before = len(frame)
    frame = frame.drop_duplicates().sort_values("open_time", ignore_index=True)
    dropped = before - len(frame)
    conflicts = frame["open_time"].duplicated(keep=False)
    if conflicts.any():
        times = frame.loc[conflicts, "open_time"].unique()[:5]
        raise DataError(f"same open_time with different values, e.g. {list(times)}")

    step = pd.Timedelta(seconds=interval_seconds(interval))
    off_grid = ~is_aligned(frame["open_time"], step)
    frame["partial"] = (frame["close_time"] - frame["open_time"]) != full_length(frame, step)
    placeholder = frame["partial"] & (frame["trades"] == 0) & ~off_grid
    off_grid_times = list(frame.loc[off_grid, "open_time"])
    placeholder_times = list(frame.loc[placeholder, "open_time"])
    frame = frame[~(off_grid | placeholder)].reset_index(drop=True)

    path = parquet_path(data_dir, symbol, interval)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".parquet.part")
    frame.to_parquet(tmp, index=False)
    tmp.replace(path)
    return BuildResult(
        path,
        len(files),
        len(frame),
        dropped,
        off_grid=off_grid_times,
        placeholders=placeholder_times,
    )
