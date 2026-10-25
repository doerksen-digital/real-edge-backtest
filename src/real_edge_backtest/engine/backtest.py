"""Bar-by-bar backtest loop.

Order inside each bar (TradingView with process_orders_on_close = true):
1. price orders (stops) that the bar reaches are filled intrabar
2. the strategy's close logic runs; market orders fill at this bar's close
3. equity is marked at the close
A stop placed at a close is therefore active from the next bar on.
"""

from dataclasses import dataclass
from decimal import Decimal

import numpy as np
import pandas as pd

from real_edge_backtest.engine.broker import Broker, Trade
from real_edge_backtest.engine.config import BrokerConfig
from real_edge_backtest.engine.fills import Bar
from real_edge_backtest.engine.strategy import Strategy

ONE_HOUR = pd.Timedelta(hours=1)


@dataclass
class Result:
    trades: list[Trade]
    equity: pd.DataFrame  # open_time, equity (Decimal)
    broker: BrokerConfig

    @property
    def closed_trades(self) -> list[Trade]:
        return [t for t in self.trades if t.exit_index is not None]


def to_ticks(prices: pd.Series, tick_size: Decimal) -> np.ndarray:
    """Exact integer ticks. Binance prices are decimal strings with at most the tick's places,
    so rounding the float only removes binary noise; anything off the tick grid is an error."""
    scaled = prices.to_numpy(dtype=float) / float(tick_size)
    ticks = np.rint(scaled)
    if np.any(np.abs(scaled - ticks) > 1e-6):
        raise ValueError("prices are not multiples of the tick size")
    return ticks.astype(np.int64)


class Backtest:
    def __init__(
        self,
        data: pd.DataFrame,
        strategy_cls: type[Strategy],
        broker: BrokerConfig,
        params: dict | None = None,
        interval: pd.Timedelta = ONE_HOUR,
    ) -> None:
        data = data.reset_index(drop=True).copy()
        data["time_close"] = data["open_time"] + interval
        self.data = data
        self.strategy_cls = strategy_cls
        self.broker_config = broker
        self.params = params or {}

    def run(self) -> Result:
        tick = self.broker_config.tick_size
        o = to_ticks(self.data["open"], tick)
        h = to_ticks(self.data["high"], tick)
        lo = to_ticks(self.data["low"], tick)
        c = to_ticks(self.data["close"], tick)
        times = list(self.data["open_time"])

        broker = Broker(self.broker_config)
        strategy = self.strategy_cls(self.data, broker, self.params)
        strategy.init()

        equity = []
        for i in range(len(self.data)):
            broker.index = i
            broker.time = times[i]
            broker.bar = Bar(int(o[i]), int(h[i]), int(lo[i]), int(c[i]))
            broker.process_price_orders()
            strategy.i = i
            strategy.next()
            equity.append(broker.equity(int(c[i])))

        return Result(
            trades=broker.trades,
            equity=pd.DataFrame({"open_time": times, "equity": equity}),
            broker=self.broker_config,
        )
