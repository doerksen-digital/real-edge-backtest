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
from real_edge_backtest.strategies.plugins import build_exits, build_filters

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
    enriched: pd.DataFrame | None = None  # per trade: entry features and excursions

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


def excursions(
    trade: Trade,
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    slippage_ticks: int,
    atr: float,
    tick: float,
) -> dict[str, float]:
    """How far a trade went for and against it, from the bars after its entry bar through its
    exit bar (or the last bar while open). Prices are unslipped: the entry is the entry bar's
    close, the exit the fill before slippage, so realized_pct matches the gross move.

    On the exit bar of a stop exit, the adverse extreme is the stop trigger and the favorable
    extreme is not counted (pessimistic: the stop is assumed to come first). On the exit bar
    of a market exit at the close, the whole bar counts.

    pct values are fractions of the entry price; atr values are in ATR at entry; mae is a
    positive distance. mfe_bar: bars after entry at which the MFE was first reached (0: none).
    """
    side, e = trade.side, trade.entry_index
    last = len(close) - 1 if trade.exit_index is None else trade.exit_index
    entry = int(close[e])
    best = worst = 0
    best_bar = 0
    for k in range(e + 1, last + 1):
        favorable = high[k] if side > 0 else low[k]
        adverse = low[k] if side > 0 else high[k]
        if k == trade.exit_index and trade.exit_by_stop:
            favorable = entry
            adverse = trade.exit_price + side * slippage_ticks
        gain = side * (int(favorable) - entry)
        if gain > best:
            best, best_bar = gain, k - e
        worst = max(worst, -side * (int(adverse) - entry))
    if trade.exit_index is None:
        realized = side * (int(close[last]) - entry)
    else:
        realized = side * (trade.exit_price + side * slippage_ticks - entry)
    atr_ok = atr > 0 and not np.isnan(atr)
    return {
        "mfe_pct": best / entry,
        "mae_pct": worst / entry,
        "mfe_atr": best * tick / atr if atr_ok else np.nan,
        "mae_atr": worst * tick / atr if atr_ok else np.nan,
        "realized_pct": realized / entry,
        "giveback_pct": (best - realized) / entry,
        "bars_held": last - e,
        "mfe_bar": best_bar,
    }


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
        filters: list[dict] | None = None,
        exits: list[dict] | None = None,
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
        self.filter_configs = list(filters or [])
        self.exit_configs = list(exits or [])
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
        # Fresh plug-in objects per run; built before init so errors come first.
        strategy.filters = build_filters(self.filter_configs)
        strategy.exits = build_exits(self.exit_configs)
        strategy.init()
        for plugin in [*strategy.filters, *strategy.exits]:
            plugin.init(strategy)

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

        bar_columns = strategy.bar_columns()
        atr = bar_columns.get("atr")
        slip = self.broker_config.slippage_ticks
        enriched = pd.DataFrame(
            [
                {
                    "number": t.number,
                    "side": "long" if t.side > 0 else "short",
                    "entry_time": t.entry_time,
                    "exit_time": t.exit_time,
                    "exit_by_stop": t.exit_by_stop,
                    **strategy.entry_features(t.entry_index, t.side),
                    **excursions(
                        t,
                        h,
                        lo,
                        c,
                        slip,
                        np.nan if atr is None else float(atr[t.entry_index]),
                        float(tick),
                    ),
                }
                for t in broker.trades
            ]
        )
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
                    **bar_columns,
                }
            ),
            broker=self.broker_config,
            missing_before=self.data["missing_before"].to_numpy(),
            min_gap_bars=self.min_gap_bars,
            counters=dict(strategy.counters),
            enriched=enriched,
        )
