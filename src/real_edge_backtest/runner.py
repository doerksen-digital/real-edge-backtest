"""Run a backtest from a RunConfig: load the dataset, pick the strategy, run the engine."""

import pandas as pd

from real_edge_backtest.data.intervals import interval_seconds
from real_edge_backtest.data.paths import parquet_path
from real_edge_backtest.engine import Backtest, Result, RunConfig
from real_edge_backtest.holdout import check_holdout
from real_edge_backtest.provenance import git_state, sha256_file, sha256_text
from real_edge_backtest.strategies import STRATEGIES


def load_candles(config: RunConfig) -> pd.DataFrame:
    path = parquet_path(config.data_dir, config.symbol, config.interval)
    if not path.exists():
        raise FileNotFoundError(f"no dataset at {path}, run 'data download' first")
    return pd.read_parquet(path)


MIN_HISTORY = pd.Timedelta(days=30)


def history_warnings(candles: pd.DataFrame, start: str) -> list[str]:
    """Warn when Start leaves less than 30 days of history to settle the indicators."""
    first = candles["open_time"].iloc[0]
    begin = pd.Timestamp(start)
    begin = begin.tz_localize("UTC") if begin.tzinfo is None else begin.tz_convert("UTC")
    available = int((candles["open_time"] < begin).sum())
    if begin - first < MIN_HISTORY:
        return [
            f"Start {begin:%Y-%m-%d %H:%M} UTC is less than 30 days after the first candle "
            f"({first:%Y-%m-%d %H:%M} UTC): only {available} candles of history before Start. "
            "Early indicator values, mainly the EMAs seeded with their first value, are not "
            "settled."
        ]
    return []


def run_metadata(config: RunConfig) -> dict:
    """What a report needs to know about a run besides its trades and equity."""
    params = {**STRATEGIES[config.strategy].params, **config.params}
    b = config.broker
    data = parquet_path(config.data_dir, config.symbol, config.interval)
    return {
        "name": config.name,
        "strategy": config.strategy,
        "symbol": config.symbol,
        "interval": config.interval,
        "window": {"start": params.get("start"), "end": params.get("end")},
        "params": params,
        "broker": {
            "initial_capital": str(b.initial_capital),
            "commission_pct": str(b.commission_pct),
            "slippage_ticks": b.slippage_ticks,
            "tick_size": str(b.tick_size),
            "lot_size": str(b.lot_size),
            "point_value": str(b.point_value),
            "fill_model": b.fill_model,
        },
        "sizing": config.sizing.describe(),
        "criteria": config.criteria,
        "provenance": {
            **git_state(),
            "config_sha256": sha256_text(config.source_text),
            "data_sha256": sha256_file(data) if data.exists() else None,
        },
    }


def run_backtest(
    config: RunConfig, data: pd.DataFrame | None = None, holdout: bool = False
) -> Result:
    """Run the engine. Holdout symbols need holdout=True (research protocol)."""
    check_holdout(config.symbol, holdout)
    if config.strategy not in STRATEGIES:
        raise ValueError(f"unknown strategy {config.strategy!r}, known: {sorted(STRATEGIES)}")
    candles = load_candles(config) if data is None else data
    return Backtest(
        candles,
        STRATEGIES[config.strategy],
        config.broker,
        config.params,
        interval=pd.Timedelta(seconds=interval_seconds(config.interval)),
        min_gap_bars=config.min_gap_bars,
        sizing=config.sizing,
    ).run()
