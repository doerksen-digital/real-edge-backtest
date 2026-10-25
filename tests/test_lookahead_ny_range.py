"""Lookahead test for ny_range: cutting the data must not change any earlier trade."""

import numpy as np
import pandas as pd
import pytest

from conftest import random_walk_5m
from real_edge_backtest.engine import Backtest, BrokerConfig
from real_edge_backtest.strategies.ny_range import NyRange

BARS = 288 * 40  # 40 NY days of 5m candles
FIVE = pd.Timedelta(minutes=5)
VARIANTS = [
    {},
    {"thru_mode": "Treat as opposite breakout", "midnight_exit": "Close only in loss"},
    {"tp_mode": "From range boundary", "include_weekends": False},
]


def run(candles, model, params):
    params = {"start": "2026-01-05T00:00:00Z", **params}
    return Backtest(candles, NyRange, BrokerConfig(fill_model=model), params, interval=FIVE).run()


def trade_key(trade):
    return (trade.side, trade.lots, trade.entry_index, trade.entry_price, trade.entry_comment)


@pytest.mark.parametrize("params", VARIANTS)
@pytest.mark.parametrize("model", ["tradingview", "pessimistic"])
@pytest.mark.parametrize("seed", [1, 2])
def test_cut_does_not_change_the_past(seed, model, params):
    candles = random_walk_5m(BARS, seed)
    full = run(candles, model, params)
    assert len(full.closed_trades) > 15, "synthetic data should produce trades"

    rng = np.random.default_rng(seed)
    for cut in rng.integers(300, BARS - 1, size=4):
        part = candles.iloc[:cut].reset_index(drop=True)
        cut_run = run(part, model, params)
        for trade in cut_run.closed_trades:
            twin = full.trades[trade.number - 1]
            assert trade_key(trade) == trade_key(twin)
            assert (trade.exit_index, trade.exit_price, trade.exit_comment, trade.net_pnl) == (
                twin.exit_index,
                twin.exit_price,
                twin.exit_comment,
                twin.net_pnl,
            )
        if cut_run.trades and cut_run.trades[-1].exit_index is None:
            last = cut_run.trades[-1]
            assert trade_key(last) == trade_key(full.trades[last.number - 1])
        assert list(cut_run.equity["equity"]) == list(full.equity["equity"][:cut])
