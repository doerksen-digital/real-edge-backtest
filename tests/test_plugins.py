"""Plug-in entry filters (including deferred entries) and exit rules, with test-only plug-ins.
Default behavior without plug-ins is covered by the parity and full-run checks."""

import numpy as np
import pandas as pd
import pytest

from conftest import make_candles
from real_edge_backtest.engine import Backtest, Broker, BrokerConfig
from real_edge_backtest.engine.fills import Bar
from real_edge_backtest.experiments import param_hash, variant_params
from real_edge_backtest.strategies import plugins
from real_edge_backtest.strategies.ema_vwap import EmaVwap
from real_edge_backtest.strategies.plugins import (
    ALLOW,
    CANCEL,
    EntryFilter,
    ExitRule,
    build_filters,
    defer,
)

LONG, SHORT = 1, -1


class Confirm(EntryFilter):
    """Enter only if the cross still holds `bars` bars later, at that bar's close."""

    name = "test_confirm"
    params = {"bars": 2}
    max_defer = 5

    def on_signal(self, strategy, i, side):
        return defer(self.p["bars"])

    def on_pending(self, strategy, i, side, bars_waited):
        if bars_waited < self.p["bars"]:
            return None
        return ALLOW if side * (strategy.ema[i] - strategy.vwap[i]) > 0 else CANCEL


class TooLong(Confirm):
    name = "test_too_long"
    params = {"bars": 9}


class BlockLongs(EntryFilter):
    name = "test_block_longs"

    def on_signal(self, strategy, i, side):
        return CANCEL if side == LONG else ALLOW


class CloseAfter(ExitRule):
    name = "test_close_after"
    params = {"bars": 2}

    def on_bar(self, strategy, i, trade):
        if i - trade.entry_index >= self.p["bars"]:
            strategy.broker.close("Test exit")


@pytest.fixture(autouse=True)
def registered(monkeypatch):
    for cls in (Confirm, TooLong, BlockLongs):
        monkeypatch.setitem(plugins.FILTERS, cls.name, cls)
    monkeypatch.setitem(plugins.EXITS, CloseAfter.name, CloseAfter)


class Forced(EmaVwap):
    """Crosses at fixed bars; `above` sets EMA - VWAP per bar (+1 above, -1 below, else 0)."""

    up: tuple[int, ...] = ()
    down: tuple[int, ...] = ()
    above: dict[int, int] = {}

    def init(self) -> None:
        super().init()
        n = len(self.close)
        self.ema = np.array([float(self.above.get(i, 0)) for i in range(n)])
        self.vwap = np.zeros(n)
        self.atr = np.full(n, 0.5)
        self.cross_up = np.isin(np.arange(n), self.up)
        self.cross_down = np.isin(np.arange(n), self.down)
        self.daily_ema_prev = np.full(n, 100.0)
        self.daily_close_prev = np.full(n, 100.0)
        self.contiguous_bars = np.full(n, 10_000)


def rising(n: int = 12) -> pd.DataFrame:
    """Closes 100, 101, ... with a tight range, so no ATR stop is hit."""
    closes = [100.0 + i for i in range(n)]
    return make_candles(closes, [c + 0.1 for c in closes], [c - 0.1 for c in closes], closes)


def flat(n: int = 12) -> pd.DataFrame:
    return make_candles([100.0] * n, [100.0] * n, [100.0] * n, [100.0] * n)


def run(filters=(), exits=(), candles=None, **signals):
    strategy = type("Case", (Forced,), signals)
    params = {"start": "2025-01-01T00:00:00Z"}
    bt = Backtest(
        rising() if candles is None else candles,
        strategy,
        BrokerConfig(fill_model="tradingview"),
        params,
        filters=list(filters),
        exits=list(exits),
    )
    return bt.run()


def test_blocked_cross_still_closes_the_opposite_trade():
    result = run([{"name": "test_block_longs"}], candles=flat(), down=(1,), up=(3,))
    (trade,) = result.trades
    assert trade.side == SHORT and trade.entry_index == 1
    assert trade.exit_index == 3 and trade.exit_comment == "Cross up, exit only"


def test_confirmation_enters_at_the_confirming_close():
    result = run([{"name": "test_confirm", "bars": 2}], up=(2,), above={4: 1})
    (trade,) = result.trades
    assert trade.side == LONG and trade.entry_index == 4
    assert trade.entry_price == 10_400 + 2  # close of bar 4 plus slippage
    assert result.counters["deferred"] == 1 and result.counters["deferred_entered"] == 1


def test_confirmation_cancels_when_the_cross_no_longer_holds():
    result = run([{"name": "test_confirm", "bars": 2}], up=(2,), above={4: -1})
    assert result.trades == []
    assert result.counters["deferred_cancelled"] == 1


def test_opposite_cross_cancels_the_pending_signal():
    # long deferred at 2, cancelled by the down cross at 3, which is deferred to bar 5
    result = run([{"name": "test_confirm", "bars": 2}], up=(2,), down=(3,), above={4: 1, 5: -1})
    (trade,) = result.trades
    assert trade.side == SHORT and trade.entry_index == 5
    assert result.counters["deferred"] == 2
    assert result.counters["deferred_cancelled"] == 1 and result.counters["deferred_entered"] == 1


def test_deferred_cross_closes_the_opposite_trade_at_once():
    result = run(
        [{"name": "test_confirm", "bars": 2}],
        candles=flat(),
        down=(1,),
        up=(5,),
        above={3: -1, 7: 1},
    )
    short, long = result.trades
    assert (short.side, short.entry_index, short.exit_index) == (SHORT, 3, 5)
    assert short.exit_comment == "Cross up, exit only"
    assert (long.side, long.entry_index) == (LONG, 7)


def test_deferral_beyond_max_defer_is_rejected():
    with pytest.raises(ValueError, match="deferred 9 bars, allowed 1 to 5"):
        run([{"name": "test_too_long"}], up=(2,))


def test_exit_rule_closes_at_the_close():
    result = run(exits=[{"name": "test_close_after", "bars": 2}], up=(1,))
    (trade,) = result.trades
    assert (trade.entry_index, trade.exit_index, trade.exit_comment) == (1, 3, "Test exit")


def test_unknown_plugins_and_parameters_are_rejected():
    with pytest.raises(ValueError, match="unknown entry filter plug-in 'nope'"):
        build_filters([{"name": "nope"}])
    with pytest.raises(ValueError, match="unknown parameters"):
        build_filters([{"name": "test_confirm", "bar": 3}])


def test_move_stop_only_tightens():
    broker = Broker(BrokerConfig())
    broker.bar = Bar(10_000, 10_000, 10_000, 10_000)
    broker.entry(LONG, 1, "long")
    broker.exit_stop("L-Stop", 100, "ATR stop")  # 99.00
    broker.move_stop("L-Stop", 9_950)
    assert broker.orders["L-Stop"].level == 9_950
    broker.move_stop("L-Stop", 9_920)  # looser: ignored
    assert broker.orders["L-Stop"].level == 9_950
    assert broker.orders["L-Stop"].comment == "Trailing stop"


def test_plugins_and_timeframe_are_part_of_the_variant_only_when_set():
    meta = {"params": {"ema_length": 9}}
    assert param_hash(variant_params(meta)) == param_hash(meta["params"])
    with_filter = {**meta, "filters": [{"name": "test_confirm", "bars": 2}]}
    with_tf = {**meta, "timeframe": "4h"}
    hashes = {param_hash(variant_params(m)) for m in (meta, with_filter, with_tf)}
    assert len(hashes) == 3
