"""Gaps: positions live through them, stops gapped past fill at the open, entries wait until
the indicators span gap-free candles again, and trades across a gap are marked."""

import numpy as np
import pandas as pd
import pytest

from conftest import make_candles
from real_edge_backtest.engine import Backtest, BrokerConfig
from real_edge_backtest.engine.backtest import gap_columns
from real_edge_backtest.engine.results import trades_frame
from real_edge_backtest.strategies.ema_vwap import EmaVwap

LONG, SHORT = 1, -1


def test_gap_columns():
    times = pd.Series(
        pd.to_datetime(
            [
                "2026-01-01 00:00",
                "2026-01-01 01:00",
                "2026-01-01 03:00",
                "2026-01-01 04:00",
                "2026-01-01 08:00",
                "2026-01-01 09:00",
            ]
        )
    )
    missing, contiguous = gap_columns(times, pd.Timedelta(hours=1), min_gap_bars=3)
    assert list(missing) == [0, 0, 1, 0, 3, 0]
    # the 1-candle gap is below the threshold and does not restart the count
    assert list(contiguous) == [1, 2, 3, 4, 1, 2]


class Forced(EmaVwap):
    """Indicators forced valid, crosses at fixed bar numbers, no trend filter. The gap columns
    (contiguous_bars) are the real ones from Backtest."""

    up: tuple[int, ...] = ()
    down: tuple[int, ...] = ()

    def init(self) -> None:
        super().init()
        n = len(self.close)
        self.ema = np.zeros(n)
        self.vwap = np.zeros(n)
        self.atr = np.full(n, 0.5)  # stop 2 * 0.5 = 1.00 = 100 ticks
        self.cross_up = np.isin(np.arange(n), self.up)
        self.cross_down = np.isin(np.arange(n), self.down)
        self.daily_ema_prev = np.full(n, 100.0)
        self.daily_close_prev = np.full(n, 100.0)


def candles_with_gap(n: int, gap_after: int, missing: int, after_gap_open: float | None = None):
    """n hourly bars at 100.00, then `missing` hours removed after bar `gap_after`."""
    prices = [100.0] * (n + missing)
    c = make_candles(prices, prices, prices, prices)
    c = c.drop(index=range(gap_after + 1, gap_after + 1 + missing)).reset_index(drop=True)
    if after_gap_open is not None:
        i = gap_after + 1
        c.loc[i, ["open", "high", "low", "close"]] = after_gap_open
    return c


def run(candles, model="pessimistic", **signals):
    strategy = type("Case", (Forced,), signals)
    params = {"start": "2025-01-01T00:00:00Z"}
    return Backtest(candles, strategy, BrokerConfig(fill_model=model), params).run()


@pytest.mark.parametrize("model", ["tradingview", "pessimistic"])
@pytest.mark.parametrize(
    ("side", "gap_open", "expected"), [(LONG, 98.50, 9_848), (SHORT, 101.50, 10_152)]
)
def test_stop_gapped_past_after_a_gap_fills_at_the_open(model, side, gap_open, expected):
    # Entry at bar 30's close (100.02 long / 99.98 short), stop 100 ticks away (99.02 / 100.98).
    candles = candles_with_gap(40, gap_after=31, missing=5, after_gap_open=gap_open)
    signal = {"up": (30,)} if side == LONG else {"down": (30,)}
    result = run(candles, model, **signal)
    trade = result.trades[0]
    assert trade.side == side
    assert trade.exit_comment == "ATR stop"
    assert trade.exit_index == 32  # the first bar after the gap
    assert trade.exit_price == expected  # that bar's open, slippage against the trader
    assert result.touches_gap(trade)


def test_open_position_survives_a_gap():
    candles = candles_with_gap(40, gap_after=31, missing=5)
    result = run(candles, up=(30,))
    trade = result.trades[0]
    assert trade.exit_index is None or trade.exit_comment == "Test end"
    frame = trades_frame(result)
    assert bool(frame.loc[0, "touches_gap"])


def test_cross_after_a_long_gap_is_ignored_until_indicators_recover():
    # 3 missing candles after bar 40. Bar 41 is the first after the gap; 24 contiguous bars
    # exist again from bar 64 on.
    candles = candles_with_gap(80, gap_after=40, missing=3)
    result = run(candles, up=(41, 63, 64))
    assert [t.entry_index for t in result.trades] == [64]
    assert result.counters["ignored_after_gap"] == 2
    assert result.gap_summary() == {
        "count": 1,
        "missing_candles": 3,
        "above_threshold": 1,
        "min_gap_bars": 3,
    }


def test_ignored_cross_does_not_close_the_open_trade():
    candles = candles_with_gap(80, gap_after=40, missing=3)
    result = run(candles, up=(30,), down=(41,))
    trade = result.trades[0]
    assert trade.side == LONG and trade.exit_index != 41


def test_short_gap_below_threshold_does_not_block():
    candles = candles_with_gap(80, gap_after=40, missing=2)
    result = run(candles, up=(41,))
    assert [t.entry_index for t in result.trades] == [41]
    assert result.gap_summary()["above_threshold"] == 0


def test_threshold_is_configurable():
    candles = candles_with_gap(80, gap_after=40, missing=2)
    strategy = type("Case", (Forced,), {"up": (41,)})
    params = {"start": "2025-01-01T00:00:00Z"}
    result = Backtest(candles, strategy, BrokerConfig(), params, min_gap_bars=2).run()
    assert result.trades == []
    assert result.counters["ignored_after_gap"] == 1


def test_trade_between_gaps_is_not_marked():
    candles = candles_with_gap(80, gap_after=10, missing=1)
    result = run(candles, up=(30,), down=(35,))
    assert not result.touches_gap(result.trades[0])
