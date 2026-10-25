"""Bracket exits: a stop and a limit at absolute levels, one cancelling the other. Prices in
ticks of 0.01, lots of 0.00001, slippage 2 ticks."""

import numpy as np
import pandas as pd
import pytest

from real_edge_backtest.engine import Broker, BrokerConfig
from real_edge_backtest.engine.backtest import excursions
from real_edge_backtest.engine.fills import Bar

LONG, SHORT = 1, -1
MODELS = ["tradingview", "pessimistic"]


def at(b: Broker, i: int, o: int, h: int, lo: int, c: int) -> None:
    b.index = i
    b.time = pd.Timestamp("2026-01-01T00:00:00Z") + pd.Timedelta(minutes=5 * i)
    b.bar = Bar(o, h, lo, c)


def bracket(model: str, side: int = LONG) -> Broker:
    """Entry at the close of 10,000 (fill 10,002 long, 9,998 short), stop 100 below / above,
    target 200 above / below the close."""
    b = Broker(BrokerConfig(fill_model=model))
    at(b, 0, 10_000, 10_000, 10_000, 10_000)
    b.entry(side, 100_000, "Long" if side == LONG else "Short")
    name = "Long exit" if side == LONG else "Short exit"
    b.exit_bracket("SL", 10_000 - side * 100, "TP", 10_000 + side * 200, name)
    return b


@pytest.mark.parametrize("model", MODELS)
def test_target_fills_at_its_level_without_slippage(model):
    b = bracket(model)
    at(b, 1, 10_050, 10_250, 10_000, 10_100)
    b.process_price_orders()
    trade = b.trades[0]
    assert (trade.exit_price, trade.exit_comment, trade.exit_kind) == (10_200, "Long exit", "limit")
    assert not trade.exit_by_stop and not trade.both_in_bar
    assert b.orders == {}  # the stop was cancelled with it


@pytest.mark.parametrize("model", MODELS)
def test_stop_fills_at_its_level_minus_slippage(model):
    b = bracket(model)
    at(b, 1, 9_950, 9_990, 9_850, 9_880)
    b.process_price_orders()
    trade = b.trades[0]
    assert (trade.exit_price, trade.exit_kind, trade.exit_by_stop) == (9_898, "stop", True)
    assert b.orders == {}


@pytest.mark.parametrize("model", MODELS)
def test_short_bracket_mirrors(model):
    b = bracket(model, SHORT)
    assert (b.orders["SL"].level, b.orders["TP"].level) == (10_100, 9_800)
    at(b, 1, 9_950, 9_990, 9_750, 9_900)
    b.process_price_orders()
    assert (b.trades[0].exit_price, b.trades[0].exit_kind) == (9_800, "limit")


@pytest.mark.parametrize("model", MODELS)
def test_gap_past_the_stop_fills_at_the_open_with_slippage(model):
    b = bracket(model)
    at(b, 1, 9_800, 10_300, 9_700, 10_250)  # opens below the stop, later reaches the target
    b.process_price_orders()
    trade = b.trades[0]
    assert (trade.exit_price, trade.exit_kind) == (9_798, "stop")
    assert not trade.both_in_bar  # the open decided, not the fill model


@pytest.mark.parametrize("model", MODELS)
def test_gap_past_the_target_fills_at_the_open_without_slippage(model):
    b = bracket(model)
    at(b, 1, 10_300, 10_350, 9_800, 9_850)  # opens above the target, later reaches the stop
    b.process_price_orders()
    trade = b.trades[0]
    assert (trade.exit_price, trade.exit_kind) == (10_300, "limit")
    assert not trade.both_in_bar


def test_both_inside_one_bar_tradingview_follows_the_path():
    # Open nearer the low: open, low, high, close. The stop (9,900) comes first.
    b = bracket("tradingview")
    at(b, 1, 9_950, 10_250, 9_850, 10_100)
    b.process_price_orders()
    assert (b.trades[0].exit_kind, b.trades[0].both_in_bar) == ("stop", True)
    # Open nearer the high: open, high, low, close. The target (10,200) comes first.
    b = bracket("tradingview")
    at(b, 1, 10_150, 10_250, 9_850, 9_900)
    b.process_price_orders()
    assert (b.trades[0].exit_kind, b.trades[0].exit_price, b.trades[0].both_in_bar) == (
        "limit",
        10_200,
        True,
    )


def test_both_inside_one_bar_pessimistic_takes_the_stop():
    b = bracket("pessimistic")
    at(b, 1, 10_150, 10_250, 9_850, 9_900)
    b.process_price_orders()
    assert (b.trades[0].exit_kind, b.trades[0].exit_price, b.trades[0].both_in_bar) == (
        "stop",
        9_898,
        True,
    )


@pytest.mark.parametrize("model", MODELS)
def test_neither_level_reached_keeps_both_orders(model):
    b = bracket(model)
    at(b, 1, 10_000, 10_199, 9_901, 10_050)
    b.process_price_orders()
    assert b.position == 100_000 and set(b.orders) == {"SL", "TP"}


def test_stop_on_the_wrong_side_is_rejected():
    b = Broker(BrokerConfig())
    at(b, 0, 10_000, 10_000, 10_000, 10_000)
    b.entry(LONG, 100_000, "Long")
    with pytest.raises(ValueError, match="losing side"):
        b.exit_bracket("SL", 10_300, "TP", 10_200, "Long exit")


def test_bracket_without_a_position_does_nothing():
    b = Broker(BrokerConfig())
    at(b, 0, 10_000, 10_000, 10_000, 10_000)
    b.exit_bracket("SL", 9_900, "TP", 10_200, "Long exit")
    assert b.orders == {}


def test_excursions_of_a_target_exit_use_the_unslipped_limit():
    b = bracket("pessimistic")
    at(b, 1, 10_050, 10_250, 9_950, 10_100)
    b.process_price_orders()
    high = np.array([10_000, 10_250])
    low = np.array([10_000, 9_950])
    close = np.array([10_000, 10_100])
    x = excursions(b.trades[0], high, low, close, 2, np.nan, 0.01)
    assert x["mfe_pct"] == pytest.approx(200 / 10_000)  # capped at the limit, not the high
    assert x["realized_pct"] == pytest.approx(200 / 10_000)  # no slippage to undo
    assert x["mae_pct"] == pytest.approx(50 / 10_000)
