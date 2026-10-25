"""Run a backtest from a RunConfig: load the dataset, pick the strategy, run the engine, and
(execute) write the run folder and its experiment log line."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from real_edge_backtest import experiments
from real_edge_backtest.analysis.metrics import Analysis, analyze, load_run
from real_edge_backtest.data.intervals import interval_seconds
from real_edge_backtest.data.paths import parquet_path
from real_edge_backtest.engine import Backtest, Result, RunConfig
from real_edge_backtest.engine.results import write_run
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
        **({"overrides": config.overrides} if config.overrides else {}),
        "provenance": {
            **git_state(),
            "config_sha256": sha256_text(config.fingerprint_text),
            "data_sha256": sha256_file(data) if data.exists() else None,
        },
    }


@dataclass
class Execution:
    folder: Path
    meta: dict[str, Any]
    result: Result
    analysis: Analysis
    variants: int  # parameter sets of this strategy family logged so far, this run included


def execute(config: RunConfig, holdout: bool = False) -> Execution:
    """One logged run: holdout check, seen-window check, engine, run folder, log line."""
    is_holdout = check_holdout(config.symbol, holdout)
    meta = run_metadata(config)
    meta["holdout"] = is_holdout
    entries = experiments.read_log(config.experiment_log)
    window = meta["window"]
    meta["seen_window"] = experiments.seen_window(
        entries, config.strategy, window["start"], window["end"]
    )
    candles = load_candles(config)
    meta["first_candle"] = candles["open_time"].iloc[0]
    meta["warnings"] = history_warnings(candles, window["start"])
    result = run_backtest(config, candles, holdout=holdout)
    meta["gaps"] = {
        **result.gap_summary(),
        "ignored_signals": result.counters.get("ignored_after_gap", 0),
    }
    folder = write_run(result, config.runs_dir, config.name, config.source_text, meta)
    a = analyze(load_run(folder))
    entry = experiments.make_entry(
        meta,
        {
            "trades": a.stats["trades"],
            "net_pnl": a.stats["net_pnl"],
            "return": a.total_return,
            "profit_factor": a.stats["profit_factor"],
            "max_drawdown_pct": a.max_drawdown[1],
            "time_in_market": a.time_in_market,
            "passed": a.passed,
        },
        folder.as_posix(),
    )
    experiments.append(config.experiment_log, entry)
    variants = experiments.variant_count([*entries, entry], config.strategy)
    return Execution(folder, meta, result, a, variants)


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
