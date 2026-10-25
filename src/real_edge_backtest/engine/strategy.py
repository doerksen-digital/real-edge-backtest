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


class Strategy:
    params: dict[str, Any] = {}

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

    def init(self) -> None:
        """Build indicators. Override."""

    def next(self) -> None:
        """Bar logic at the close of bar self.i. Override."""

    @property
    def equity(self) -> Decimal:
        """strategy.equity at this close, as used for sizing (see Broker.sizing_equity)."""
        assert self.broker.bar is not None
        return self.broker.sizing_equity(self.broker.bar.close)

    @staticmethod
    def valid(*values: float) -> bool:
        return not any(np.isnan(v) for v in values)
