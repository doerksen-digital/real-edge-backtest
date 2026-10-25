"""Validate a stored kline dataset. Gaps are reported, never filled."""

from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from real_edge_backtest.data.intervals import interval_seconds
from real_edge_backtest.data.paths import parquet_path
from real_edge_backtest.data.store import full_length, is_aligned


@dataclass
class Gap:
    start: pd.Timestamp
    end: pd.Timestamp
    missing: int
    duration: pd.Timedelta


@dataclass
class CheckReport:
    symbol: str
    interval: str
    rows: int
    first_open: pd.Timestamp
    last_open: pd.Timestamp
    duplicates: int
    not_increasing: int
    misaligned_open: int
    wrong_close: int
    ohlc_errors: int
    negative_volume: int
    missing_values: int
    gaps: list[Gap] = field(default_factory=list)
    partial: list[pd.Timestamp] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not (
            self.duplicates
            or self.not_increasing
            or self.misaligned_open
            or self.wrong_close
            or self.ohlc_errors
            or self.negative_volume
            or self.missing_values
        )


def check_frame(frame: pd.DataFrame, symbol: str, interval: str) -> CheckReport:
    step = pd.Timedelta(seconds=interval_seconds(interval))
    opens = frame["open_time"]

    diffs = opens.diff().iloc[1:]
    misaligned = ~is_aligned(opens, step)
    # A complete candle closes at interval - 1 source unit. A partial candle must be flagged,
    # close after it opens and before a complete candle would, and contain trades.
    length = frame["close_time"] - opens
    full = full_length(frame, step)
    is_partial = length != full
    wrong_close = (is_partial != frame["partial"]) | (
        is_partial & ((length <= pd.Timedelta(0)) | (length > full) | (frame["trades"] == 0))
    )

    high, low, op, cl = frame["high"], frame["low"], frame["open"], frame["close"]
    ohlc_bad = (high < op) | (high < cl) | (high < low) | (low > op) | (low > cl)
    volume_columns = [
        "volume",
        "quote_volume",
        "taker_buy_base_volume",
        "taker_buy_quote_volume",
        "trades",
    ]
    negative = (frame[volume_columns] < 0).any(axis=1)

    gaps = []
    for position in diffs.index[diffs > step]:
        before = opens.iloc[position - 1]
        after = opens.iloc[position]
        missing = int((after - before) / step) - 1
        gaps.append(Gap(before + step, after - step, missing, missing * step))

    return CheckReport(
        symbol=symbol,
        interval=interval,
        rows=len(frame),
        first_open=opens.iloc[0],
        last_open=opens.iloc[-1],
        duplicates=int(opens.duplicated().sum()),
        not_increasing=int((diffs <= pd.Timedelta(0)).sum()),
        misaligned_open=int(misaligned.sum()),
        wrong_close=int(wrong_close.sum()),
        ohlc_errors=int(ohlc_bad.sum()),
        negative_volume=int(negative.sum()),
        missing_values=int(frame.isna().any(axis=1).sum()),
        gaps=gaps,
        partial=list(opens[is_partial]),
    )


def check_dataset(data_dir: Path, symbol: str, interval: str) -> CheckReport:
    symbol = symbol.upper()
    path = parquet_path(data_dir, symbol, interval)
    if not path.exists():
        raise FileNotFoundError(f"no dataset at {path}, run 'data download' first")
    frame = pd.read_parquet(path)
    return check_frame(frame, symbol, interval)


def _fmt(ts: pd.Timestamp) -> str:
    return ts.strftime("%Y-%m-%d %H:%M UTC")


def format_report(report: CheckReport, largest: int = 5) -> str:
    """Human-readable report. A gap runs from the first to the last missing candle open time."""
    lines = [
        f"Dataset {report.symbol} {report.interval}",
        f"  first candle      {_fmt(report.first_open)}",
        f"  last candle       {_fmt(report.last_open)}",
        f"  rows              {report.rows}",
        f"  duplicates        {report.duplicates}",
        f"  not increasing    {report.not_increasing}",
        f"  misaligned open   {report.misaligned_open}",
        f"  wrong close time  {report.wrong_close}",
        f"  partial candles   {len(report.partial)} (closed early before an outage, kept)",
        f"  OHLC errors       {report.ohlc_errors}",
        f"  negative volume   {report.negative_volume}",
        f"  missing values    {report.missing_values}",
        f"  gaps              {len(report.gaps)} "
        f"({sum(g.missing for g in report.gaps)} missing candles, not filled)",
    ]
    if report.gaps:
        lines.append("")
        lines.append("Gaps (first and last missing candle open time):")
        lines.extend(
            f"  {_fmt(g.start)}  ->  {_fmt(g.end)}  missing {g.missing:>4}  ({g.duration})"
            for g in report.gaps
        )
        lines.append("")
        lines.append(f"Largest {min(largest, len(report.gaps))} gaps:")
        top = sorted(report.gaps, key=lambda g: g.missing, reverse=True)[:largest]
        lines.extend(
            f"  {_fmt(g.start)}  ->  {_fmt(g.end)}  missing {g.missing:>4}  ({g.duration})"
            for g in top
        )
    if report.partial:
        lines.append("")
        lines.append("Partial candles (open time):")
        lines.extend(f"  {_fmt(ts)}" for ts in report.partial)
    lines.append("")
    lines.append("RESULT: OK" if report.ok else "RESULT: FAILED")
    return "\n".join(lines)
