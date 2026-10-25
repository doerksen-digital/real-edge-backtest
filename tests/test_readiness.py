"""Readiness: no trade before every indicator exists; Start does not change indicator values."""

import numpy as np
import pandas as pd

from conftest import make_candles, random_walk
from real_edge_backtest.engine import Backtest, Broker, BrokerConfig
from real_edge_backtest.runner import history_warnings
from real_edge_backtest.strategies.ema_vwap import EmaVwap

INDICATORS = ("ema", "vwap", "atr", "cross_up", "cross_down", "daily_ema_prev", "daily_close_prev")


def indicators(candles: pd.DataFrame, start: str) -> dict[str, np.ndarray]:
    data = candles.assign(time_close=candles["open_time"] + pd.Timedelta(hours=1))
    strategy = EmaVwap(data, Broker(BrokerConfig()), {"use_trend": True, "start": start})
    strategy.init()
    return {name: getattr(strategy, name) for name in INDICATORS}


def test_different_starts_give_identical_indicators_on_overlapping_bars():
    candles = random_walk(24 * 120, 11)
    early = indicators(candles, "2025-01-10T00:00:00Z")
    late = indicators(candles, "2025-03-01T00:00:00Z")
    overlap = candles["open_time"] >= pd.Timestamp("2025-03-01T00:00:00Z")
    for name in INDICATORS:
        np.testing.assert_array_equal(early[name][overlap], late[name][overlap], err_msg=name)


class ForcedCrosses(EmaVwap):
    """Real daily values; EMA, VWAP and ATR forced valid, crosses at fixed bars."""

    up_bars = (2, 30)

    def init(self) -> None:
        super().init()
        n = len(self.close)
        self.ema = np.zeros(n)
        self.vwap = np.zeros(n)
        self.atr = np.full(n, 0.5)
        self.cross_up = np.isin(np.arange(n), self.up_bars)
        self.cross_down = np.zeros(n, dtype=bool)


def test_no_trade_until_previous_day_values_exist():
    n = 48  # two UTC days from 2026-01-01 00:00
    candles = make_candles([100.0] * n, [100.0] * n, [100.0] * n, [100.0] * n)
    params = {"use_trend": False, "start": "2025-01-01T00:00:00Z"}
    result = Backtest(candles, ForcedCrosses, BrokerConfig(), params).run()
    # Day 1 has no previous completed day: the cross at bar 2 is ignored. Bar 30 is on day 2.
    assert [t.entry_index for t in result.trades] == [30]


def test_history_warning_when_start_is_close_to_the_first_candle():
    candles = random_walk(24 * 60, 3)  # from 2025-01-01
    short = history_warnings(candles, "2025-01-11T00:00:00Z")
    assert len(short) == 1 and "only 240 candles of history" in short[0]
    assert history_warnings(candles, "2025-02-01T00:00:00Z") == []
