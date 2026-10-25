"""Broker and strategy-logic tests on synthetic bars. Prices in ticks of 0.01, lots of 0.00001."""

import math
from decimal import Decimal

import numpy as np
import pandas as pd
import pytest

from conftest import make_candles
from real_edge_backtest.engine import Backtest, Broker, BrokerConfig, Result
from real_edge_backtest.engine.fills import Bar, PriceOrder
from real_edge_backtest.strategies.ema_vwap import EmaVwap, position_lots

LONG, SHORT = 1, -1


def broker(model: str = "tradingview") -> Broker:
    return Broker(BrokerConfig(fill_model=model))


def at(b: Broker, i: int, o: int, h: int, lo: int, c: int) -> None:
    b.index = i
    b.time = pd.Timestamp("2026-01-01T00:00:00Z") + pd.Timedelta(hours=i)
    b.bar = Bar(o, h, lo, c)


# Market fills, slippage, commission -------------------------------------------------------


def test_market_long_fills_at_close_plus_slippage_with_percent_commission():
    b = broker()
    at(b, 0, 1_000_000, 1_000_000, 1_000_000, 1_000_000)  # close 10,000.00
    assert b.entry(LONG, 100_000, "EMA above VWAP")  # 1 BTC
    trade = b.open_trade
    assert trade.entry_price == 1_000_002  # 10,000.02
    # 1 * 10,000.02 * 0.05% = 5.00001, exact
    assert trade.entry_commission == Decimal("5.00001")


def test_market_short_fills_at_close_minus_slippage():
    b = broker()
    at(b, 0, 1_000_000, 1_000_000, 1_000_000, 1_000_000)
    b.entry(SHORT, 100_000, "EMA below VWAP")
    assert b.open_trade.entry_price == 999_998


def test_close_books_net_pnl_after_both_commissions():
    b = broker()
    at(b, 0, 10_000, 10_000, 10_000, 10_000)  # 100.00
    b.entry(LONG, 100_000, "in")  # 1 BTC at 100.02
    at(b, 1, 11_000, 11_000, 11_000, 11_000)  # 110.00
    b.close("out")  # at 109.98
    trade = b.trades[0]
    assert trade.exit_price == 10_998
    assert trade.gross_pnl == Decimal("9.96")
    assert trade.commission == Decimal("0.05001") + Decimal("0.05499")
    assert trade.net_pnl == Decimal("9.855")
    assert b.net_profit == trade.net_pnl
    assert b.position == 0


# Stop fills --------------------------------------------------------------------------------


def long_with_stop(model: str, stop_ticks: int = 100) -> Broker:
    b = broker(model)
    at(b, 0, 10_000, 10_000, 10_000, 10_000)
    b.entry(LONG, 100_000, "in")  # fill 10,002
    b.exit_stop("L-Stop", stop_ticks, "ATR stop")  # level 9,902
    return b


@pytest.mark.parametrize("model", ["tradingview", "pessimistic"])
def test_stop_fills_at_level_minus_slippage(model):
    b = long_with_stop(model)
    assert b.orders["L-Stop"].level == 9_902
    at(b, 1, 10_000, 10_010, 9_800, 9_900)
    b.process_price_orders()
    assert b.trades[0].exit_price == 9_900
    assert b.trades[0].exit_comment == "ATR stop"


@pytest.mark.parametrize("model", ["tradingview", "pessimistic"])
def test_stop_gapped_past_fills_at_open(model):
    b = long_with_stop(model)
    at(b, 1, 9_850, 9_870, 9_700, 9_800)  # opens below the 9,902 stop
    b.process_price_orders()
    assert b.trades[0].exit_price == 9_848  # open minus slippage


@pytest.mark.parametrize("model", ["tradingview", "pessimistic"])
def test_stop_not_reached_stays_open(model):
    b = long_with_stop(model)
    at(b, 1, 10_000, 10_100, 9_903, 10_050)
    b.process_price_orders()
    assert b.position == 100_000
    assert "L-Stop" in b.orders


def test_short_stop_fills_above_level_plus_slippage():
    b = broker()
    at(b, 0, 10_000, 10_000, 10_000, 10_000)
    b.entry(SHORT, 100_000, "in")  # fill 9,998
    b.exit_stop("S-Stop", 100, "ATR stop")  # level 10,098
    at(b, 1, 10_000, 10_200, 9_990, 10_150)
    b.process_price_orders()
    assert b.trades[0].exit_price == 10_100


def test_fill_models_differ_when_stop_and_target_share_a_bar():
    """Open nearer the high: TradingView's path reaches the high (target) before the low (stop).
    The pessimistic model fills the stop."""
    bar = (10_050, 10_150, 9_850, 10_000)
    results = {}
    for model in ("tradingview", "pessimistic"):
        b = long_with_stop(model, stop_ticks=102)  # stop level 9,900
        b.orders["TP"] = PriceOrder("TP", "limit", -1, 10_100, "target")
        at(b, 1, *bar)
        b.process_price_orders()
        results[model] = (b.trades[0].exit_comment, b.trades[0].exit_price)
    assert results["tradingview"] == ("target", 10_100)  # limits get no slippage
    assert results["pessimistic"] == ("ATR stop", 9_898)


# Reversal and pyramiding ------------------------------------------------------------------


def test_entry_against_position_reverses_in_one_fill():
    b = broker()
    at(b, 0, 10_000, 10_000, 10_000, 10_000)
    b.entry(LONG, 100_000, "EMA above VWAP")
    at(b, 1, 10_500, 10_500, 10_500, 10_500)
    b.entry(SHORT, 60_000, "EMA below VWAP")
    first, second = b.trades
    assert first.exit_price == second.entry_price == 10_498
    assert first.exit_comment == "EMA below VWAP"
    assert first.exit_commission == b.commission(100_000, 10_498)
    assert second.entry_commission == b.commission(60_000, 10_498)
    assert b.position == -60_000


def test_entry_in_same_direction_is_rejected():
    b = broker()
    at(b, 0, 10_000, 10_000, 10_000, 10_000)
    b.entry(LONG, 100_000, "in")
    assert not b.entry(LONG, 50_000, "again")
    assert b.position == 100_000 and len(b.trades) == 1


def test_equity_is_capital_plus_closed_net_plus_open_profit():
    b = broker()
    at(b, 0, 10_000, 10_000, 10_000, 10_000)
    b.entry(LONG, 100_000, "in")
    at(b, 1, 10_200, 10_200, 10_200, 10_200)
    b.entry(SHORT, 100_000, "flip")  # closes the long at 101.98, opens short at 101.98
    closed = b.trades[0].net_pnl
    open_profit = Decimal("-1") * (Decimal("101.00") - Decimal("101.98"))  # 1 BTC short
    assert b.open_profit(10_100) == open_profit
    assert b.equity(10_100) == Decimal("10000") + closed + open_profit


# Quantity without float errors ------------------------------------------------------------


@pytest.mark.parametrize(
    ("lots", "price"),
    [(10_002, "91529.75"), (10_005, "91529.75"), (8, "1.10"), (29, "0.30"), (11_093, "90094.01")],
)
def test_qty_formula_is_exact_on_float_traps(lots, price):
    fill = Decimal(price)
    equity = lots * Decimal("0.00001") * fill * Decimal("1.0005")  # exactly `lots` steps
    exact = position_lots(
        equity, Decimal(100), Decimal("0.05"), fill, Decimal(1), Decimal("0.00001")
    )
    assert exact == lots


def test_naive_float_formula_really_fails_on_the_trap():
    fill, lots = Decimal("91529.75"), 10_002
    equity = lots * Decimal("0.00001") * fill * Decimal("1.0005")
    naive = math.floor(float(equity) * 100 / 100 / (1 + 0.05 / 100) / float(fill) / 0.00001)
    assert naive == lots - 1


def test_qty_is_zero_without_equity():
    args = (Decimal(100), Decimal("0.05"), Decimal("100"), Decimal(1), Decimal("0.00001"))
    assert position_lots(Decimal("-5"), *args) == 0


# Strategy logic with forced signals --------------------------------------------------------


class Forced(EmaVwap):
    """EmaVwap with signal and filter arrays replaced after init. Everything else is real."""

    up: dict[int, bool] = {}
    down: dict[int, bool] = {}
    trend: dict[int, int] = {}  # +1 up, -1 down per bar
    atr_value = 0.5

    def init(self) -> None:
        super().init()
        n = len(self.close)
        self.ema = np.zeros(n)
        self.vwap = np.zeros(n)
        self.atr = np.full(n, self.atr_value)
        self.cross_up = np.array([self.up.get(i, False) for i in range(n)])
        self.cross_down = np.array([self.down.get(i, False) for i in range(n)])
        self.daily_ema_prev = np.full(n, 100.0)
        self.daily_close_prev = np.array([100.0 + self.trend.get(i, 0) for i in range(n)])
        self.contiguous_bars = np.full(n, 10_000)  # no gap block on short synthetic data


def run_forced(candles: pd.DataFrame, **signals) -> Result:
    strategy = type("Case", (Forced,), signals)
    params = {"use_trend": True, "start": "2025-01-01T00:00:00Z"}
    return Backtest(candles, strategy, BrokerConfig(fill_model="tradingview"), params).run()


def flat(n: int, price: float = 100.0) -> pd.DataFrame:
    return make_candles([price] * n, [price] * n, [price] * n, [price] * n)


def test_blocked_cross_closes_trade_but_opens_nothing():
    result = run_forced(
        flat(6),
        up={1: True},
        down={3: True},
        trend={1: 1, 3: 1},  # uptrend at bar 3 blocks the short
    )
    assert len(result.trades) == 1
    trade = result.trades[0]
    assert trade.side == LONG and trade.exit_index == 3
    assert trade.exit_comment == "Cross down, exit only"


def test_stop_inside_bar_then_cross_at_close_uses_equity_after_stop():
    o = [100.0, 100.0, 100.0, 99.5]
    h = [100.0, 100.0, 100.5, 99.5]
    lo = [100.0, 100.0, 98.5, 99.5]
    c = [100.0, 100.0, 99.5, 99.5]
    result = run_forced(
        make_candles(o, h, lo, c),
        up={1: True},
        down={2: True},
        trend={1: 1, 2: -1},
    )
    stopped, reversed_ = result.trades
    # Long at 100.02, stop 2 * 0.5 / 0.01 = 100 ticks below: 99.02, filled at 99.00 on bar 2.
    assert stopped.exit_comment == "ATR stop" and stopped.exit_price == 9_900
    assert stopped.exit_index == 2
    # Then the cross at bar 2's close opens a short sized from equity after the stop loss.
    assert reversed_.side == SHORT and reversed_.entry_index == 2
    assert reversed_.entry_price == 9_948
    equity_after_stop = Decimal("10000") + stopped.net_pnl
    expected = position_lots(
        equity_after_stop,
        Decimal(100),
        Decimal("0.05"),
        Decimal("99.48"),
        Decimal(1),
        Decimal("0.00001"),
    )
    assert reversed_.lots == expected


def test_reversal_is_sized_from_equity_net_of_open_entry_commission():
    o = h = lo = [100.0, 100.0, 101.0, 102.0, 102.0]
    c = [100.0, 100.0, 101.0, 102.0, 102.0]
    result = run_forced(
        make_candles(o, h, lo, c), up={1: True}, down={3: True}, trend={1: 1, 3: -1}
    )
    long_trade, short_trade = result.trades
    assert long_trade.exit_comment == "EMA below VWAP" and short_trade.entry_index == 3
    # strategy.equity at bar 3's close: capital + open profit - the long's entry commission
    open_profit = long_trade.lots * Decimal("0.00001") * (Decimal("102.00") - Decimal("100.02"))
    equity = Decimal("10000") + open_profit - long_trade.entry_commission
    expected = position_lots(
        equity, Decimal(100), Decimal("0.05"), Decimal("101.98"), Decimal(1), Decimal("0.00001")
    )
    assert short_trade.lots == expected


def test_sizing_equity_subtracts_open_entry_commission_only():
    b = broker()
    at(b, 0, 10_000, 10_000, 10_000, 10_000)
    b.entry(LONG, 100_000, "in")
    paid = b.open_trade.entry_commission
    assert b.sizing_equity(10_100) == b.equity(10_100) - paid
    b.close("out")
    assert b.sizing_equity(10_000) == b.equity(10_000)


def test_test_end_closes_open_position():
    candles = flat(6)
    strategy = type("Case", (Forced,), {"up": {1: True}, "trend": {1: 1}})
    params = {"use_trend": True, "start": "2025-01-01T00:00:00Z", "end": "2026-01-01T04:00:00Z"}
    result = Backtest(candles, strategy, BrokerConfig(), params).run()
    # bar 3 opens 03:00 and closes 04:00 = end: the position is closed there
    assert result.trades[0].exit_comment == "Test end"
    assert result.trades[0].exit_index == 3
