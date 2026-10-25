"""Lookahead test: cutting the data at a random point must not change anything before the cut."""

import numpy as np
import pandas as pd
import pytest

from conftest import random_walk
from real_edge_backtest.engine import Backtest, Broker, BrokerConfig
from real_edge_backtest.strategies.ema_vwap import EmaVwap

PARAMS = {"use_trend": True, "trend_length": 5, "start": "2025-01-03T00:00:00Z"}
BARS = 2400  # 100 days of hourly candles


def run(candles, model):
    return Backtest(candles, EmaVwap, BrokerConfig(fill_model=model), PARAMS).run()


def signals(candles):
    data = candles.assign(time_close=candles["open_time"] + pd.Timedelta(hours=1))
    strategy = EmaVwap(data, Broker(BrokerConfig()), PARAMS)
    strategy.init()
    return {
        "cross_up": strategy.cross_up,
        "cross_down": strategy.cross_down,
        "atr": strategy.atr,
        "daily_ema_prev": strategy.daily_ema_prev,
        "daily_close_prev": strategy.daily_close_prev,
    }


def trade_key(trade):
    return (trade.side, trade.lots, trade.entry_index, trade.entry_price, trade.entry_commission)


@pytest.mark.parametrize("model", ["tradingview", "pessimistic"])
@pytest.mark.parametrize("seed", [1, 2, 3])
def test_cut_does_not_change_the_past(seed, model):
    candles = random_walk(BARS, seed)
    full = run(candles, model)
    full_signals = signals(candles)
    assert len(full.closed_trades) > 20, "synthetic data should produce trades"

    rng = np.random.default_rng(seed)
    for cut in rng.integers(300, BARS - 1, size=4):
        part = candles.iloc[:cut].reset_index(drop=True)
        cut_signals = signals(part)
        for name, values in cut_signals.items():
            np.testing.assert_array_equal(values, full_signals[name][:cut], err_msg=name)

        cut_run = run(part, model)
        # Every trade the cut run closed is identical in the full run.
        for trade in cut_run.closed_trades:
            twin = full.trades[trade.number - 1]
            assert trade_key(trade) == trade_key(twin)
            assert (trade.exit_index, trade.exit_price, trade.net_pnl) == (
                twin.exit_index,
                twin.exit_price,
                twin.net_pnl,
            )
        # A trade still open at the cut was entered identically.
        if cut_run.trades and cut_run.trades[-1].exit_index is None:
            last = cut_run.trades[-1]
            assert trade_key(last) == trade_key(full.trades[last.number - 1])
        assert list(cut_run.equity["equity"]) == list(full.equity["equity"][:cut])
