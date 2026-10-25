"""Bar-by-bar backtest loop.

Order inside each bar (TradingView with process_orders_on_close = true):
1. price orders (stops) that the bar reaches are filled intrabar
2. the strategy's close logic runs; market orders fill at this bar's close
3. equity is marked at the close
A stop placed at a close is therefore active from the next bar on.

Gaps (missing candles) are never filled. An open position and its stop live through a gap; a
stop that the first bar after the gap opens beyond fills at that open. Each bar carries
`missing_before` (candles missing right before it) and `contiguous_bars` (bars since the last
gap of at least `min_gap_bars` missing candles, this bar included), so a strategy can wait
until its indicators span gap-free data again.
"""

from dataclasses import dataclass, field
from decimal import Decimal

import numpy as np
import pandas as pd

from real_edge_backtest.engine.broker import Broker, Trade
from real_edge_backtest.engine.config import BrokerConfig
from real_edge_backtest.engine.fills import Bar
from real_edge_backtest.engine.sizing import SizingConfig
from real_edge_backtest.engine.strategy import Strategy

ONE_HOUR = pd.Timedelta(hours=1)


@dataclass
class Result:
    trades: list[Trade]
    # open_time, time_close, open, close, position (lots), equity (Decimal), then the
    # strategy's bar_columns (e.g. atr)
    equity: pd.DataFrame
    broker: BrokerConfig
    missing_before: np.ndarray = field(default_factory=lambda: np.zeros(0, dtype=np.int64))
    min_gap_bars: int = 3
    counters: dict[str, int] = field(default_factory=dict)  # strategy counters

    @property
    def closed_trades(self) -> list[Trade]:
        return [t for t in self.trades if t.exit_index is not None]

    def touches_gap(self, trade: Trade) -> bool:
        """A candle is missing between the trade's entry bar and its exit bar (or the end)."""
        last = len(self.missing_before) - 1 if trade.exit_index is None else trade.exit_index
        return bool(self.missing_before[trade.entry_index + 1 : last + 1].any())

    def gap_summary(self) -> dict[str, int]:
        gaps = self.missing_before[self.missing_before > 0]
        return {
            "count": int(len(gaps)),
            "missing_candles": int(gaps.sum()),
            "above_threshold": int((gaps >= self.min_gap_bars).sum()),
            "min_gap_bars": self.min_gap_bars,
        }


def gap_columns(
    open_time: pd.Series, interval: pd.Timedelta, min_gap_bars: int
) -> tuple[np.ndarray, np.ndarray]:
    """missing_before and contiguous_bars per bar (see module docstring)."""
    steps = (open_time.diff() / interval).fillna(1).to_numpy(dtype=float)
    missing = np.rint(steps).astype(np.int64) - 1
    contiguous = np.empty(len(missing), dtype=np.int64)
    run = 0
    for i, m in enumerate(missing):
        run = 1 if m >= min_gap_bars else run + 1
        contiguous[i] = run
    return missing, contiguous


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
        min_gap_bars: int = 3,
        sizing: SizingConfig | None = None,
    ) -> None:
        if min_gap_bars < 1:
            raise ValueError("min_gap_bars must be at least 1")
        data = data.reset_index(drop=True).copy()
        data["time_close"] = data["open_time"] + interval
        data["missing_before"], data["contiguous_bars"] = gap_columns(
            data["open_time"], interval, min_gap_bars
        )
        self.min_gap_bars = min_gap_bars
        self.sizing = sizing or SizingConfig()
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
        strategy.sizing = self.sizing
        strategy.init()

        equity, positions = [], []
        for i in range(len(self.data)):
            broker.index = i
            broker.time = times[i]
            broker.bar = Bar(int(o[i]), int(h[i]), int(lo[i]), int(c[i]))
            broker.process_price_orders()
            strategy.i = i
            strategy.next()
            equity.append(broker.equity(int(c[i])))
            positions.append(broker.position)

        return Result(
            trades=broker.trades,
            equity=pd.DataFrame(
                {
                    "open_time": times,
                    "time_close": self.data["time_close"],
                    "open": self.data["open"],
                    "close": self.data["close"],
                    "position": positions,
                    "equity": equity,
                    **strategy.bar_columns(),
                }
            ),
            broker=self.broker_config,
            missing_before=self.data["missing_before"].to_numpy(),
            min_gap_bars=self.min_gap_bars,
            counters=dict(strategy.counters),
        )
