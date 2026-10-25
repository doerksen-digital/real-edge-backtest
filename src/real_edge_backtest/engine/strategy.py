"""Strategy base class (design in the style of backtesting.py; no code taken from it).

init() runs once on the full data and may only build indicators that are causal (every value
at index i uses inputs up to i). next() runs on each bar after that bar closed and may only read
values at indices <= self.i. The lookahead test checks both rules by cutting the data.
"""

from decimal import Decimal
from typing import Any

import numpy as np
import pandas as pd

from real_edge_backtest.engine.broker import Broker
from real_edge_backtest.engine.sizing import SizingConfig


class Strategy:
    params: dict[str, Any] = {}
    sizing: SizingConfig = SizingConfig()  # set per run by Backtest
    filters: list = []  # entry filter plug-ins, set per run by Backtest
    exits: list = []  # exit rule plug-ins, set per run by Backtest

    def __init__(self, data: pd.DataFrame, broker: Broker, params: dict[str, Any]) -> None:
        unknown = set(params) - set(self.params)
        if unknown:
            raise ValueError(f"unknown strategy parameters: {sorted(unknown)}")
        self.data = data
        self.broker = broker
        self.p = {**self.params, **params}
        self.i = -1
        self.open = data["open"].to_numpy(dtype=float)
        self.high = data["high"].to_numpy(dtype=float)
        self.low = data["low"].to_numpy(dtype=float)
        self.close = data["close"].to_numpy(dtype=float)
        self.volume = data["volume"].to_numpy(dtype=float)
        self.time = data["open_time"]
        self.time_close = data["time_close"]
        n = len(data)
        # Set by Backtest; a bare frame counts as gap-free.
        self.missing_before = (
            data["missing_before"].to_numpy() if "missing_before" in data else np.zeros(n, int)
        )
        self.contiguous_bars = (
            data["contiguous_bars"].to_numpy() if "contiguous_bars" in data else np.arange(1, n + 1)
        )
        self.counters: dict[str, int] = {}

    def init(self) -> None:
        """Build indicators. Override."""

    def next(self) -> None:
        """Bar logic at the close of bar self.i. Override."""

    def entry_features(self, i: int, side: int) -> dict[str, Any]:
        """Values known at the close of bar i that describe an entry there on `side` (+1 long,
        -1 short), written to trades_enriched.csv. May only read indices <= i. Override."""
        return {}

    def bar_columns(self) -> dict[str, np.ndarray]:
        """Per-bar indicator values written to equity.csv for the report. Override."""
        return {}

    @property
    def equity(self) -> Decimal:
        """strategy.equity at this close, as used for sizing (see Broker.sizing_equity)."""
        assert self.broker.bar is not None
        return self.broker.sizing_equity(self.broker.bar.close)

    @staticmethod
    def valid(*values: float) -> bool:
        return not any(np.isnan(v) for v in values)
