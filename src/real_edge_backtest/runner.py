"""Run a backtest from a RunConfig: load the dataset, pick the strategy, run the engine."""

import pandas as pd

from real_edge_backtest.data.intervals import interval_seconds
from real_edge_backtest.data.paths import parquet_path
from real_edge_backtest.engine import Backtest, Result, RunConfig
from real_edge_backtest.strategies import STRATEGIES


def load_candles(config: RunConfig) -> pd.DataFrame:
    path = parquet_path(config.data_dir, config.symbol, config.interval)
    if not path.exists():
        raise FileNotFoundError(f"no dataset at {path}, run 'data download' first")
    return pd.read_parquet(path)


def run_backtest(config: RunConfig, data: pd.DataFrame | None = None) -> Result:
    if config.strategy not in STRATEGIES:
        raise ValueError(f"unknown strategy {config.strategy!r}, known: {sorted(STRATEGIES)}")
    candles = load_candles(config) if data is None else data
    return Backtest(
        candles,
        STRATEGIES[config.strategy],
        config.broker,
        config.params,
        interval=pd.Timedelta(seconds=interval_seconds(config.interval)),
    ).run()
