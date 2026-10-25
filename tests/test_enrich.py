"""Trade enrichment: entry features use nothing after the entry bar, excursions by hand."""

from decimal import Decimal

import numpy as np
import pandas as pd
import pytest

from conftest import random_walk
from real_edge_backtest.engine import Backtest, Broker, BrokerConfig, Trade
from real_edge_backtest.engine.backtest import excursions
from real_edge_backtest.engine.results import write_run
from real_edge_backtest.strategies.ema_vwap import EmaVwap

PARAMS = {"use_trend": True, "trend_length": 5, "start": "2025-01-10T00:00:00Z"}
BARS = 2400


def features_at(candles: pd.DataFrame, i: int, side: int) -> dict:
    data = Backtest(candles, EmaVwap, BrokerConfig(), PARAMS).data
    strategy = EmaVwap(data, Broker(BrokerConfig()), PARAMS)
    strategy.init()
    return strategy.entry_features(i, side)


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_entry_features_use_nothing_after_the_entry_bar(seed):
    candles = random_walk(BARS, seed)
    result = Backtest(candles, EmaVwap, BrokerConfig(), PARAMS).run()
    enriched = result.enriched.set_index("number")
    assert len(result.trades) > 20
    full = Backtest(candles, EmaVwap, BrokerConfig(), PARAMS).data
    strategy = EmaVwap(full, Broker(BrokerConfig()), PARAMS)
    strategy.init()
    for trade in result.trades[::3]:
        i = trade.entry_index
        # Cut right after the entry bar: every feature must be the same.
        cut = features_at(candles.iloc[: i + 1].reset_index(drop=True), i, trade.side)
        assert cut.keys() == strategy.entry_features(i, trade.side).keys()
        np.testing.assert_equal(cut, strategy.entry_features(i, trade.side))
        for name, value in cut.items():
            np.testing.assert_equal(enriched.loc[trade.number, name], value, err_msg=name)
    assert set(enriched["crosses_48"].dropna()) and enriched["vol_ratio_7d"].notna().any()


def trade(side, exit_index, exit_price, by_stop=False):
    t = Trade(1, side, 1, 0, pd.Timestamp("2026-01-01", tz="UTC"), 10_000, "", Decimal(0))
    t.exit_index, t.exit_price, t.exit_by_stop = exit_index, exit_price, by_stop
    return t


def run_excursions(t, high, low, close):
    arrays = (np.array(high), np.array(low), np.array(close))
    return excursions(t, *arrays, slippage_ticks=2, atr=1.0, tick=0.01)


def test_long_market_exit():
    # entry at the close of bar 0 (100.00), exit at the close of bar 3 (102.00, filled 101.98)
    x = run_excursions(
        trade(1, 3, 10_198),
        high=[10_000, 10_300, 10_100, 10_250],
        low=[10_000, 9_900, 9_950, 10_150],
        close=[10_000, 10_100, 10_050, 10_200],
    )
    assert x["mfe_pct"] == pytest.approx(0.03) and x["mfe_bar"] == 1
    assert x["mae_pct"] == pytest.approx(0.01)
    assert x["realized_pct"] == pytest.approx(0.02)
    assert x["giveback_pct"] == pytest.approx(0.01)
    assert (x["mfe_atr"], x["mae_atr"]) == pytest.approx((3.0, 1.0))  # ATR 1.00
    assert x["bars_held"] == 3


def test_long_stop_exit_caps_the_exit_bar():
    # stop at 99.00 filled 98.98; the stop bar reaches 104.00 and 98.00, neither counts
    x = run_excursions(
        trade(1, 2, 9_898, by_stop=True),
        high=[10_000, 10_100, 10_400],
        low=[10_000, 9_950, 9_800],
        close=[10_000, 10_000, 9_900],
    )
    assert x["mfe_pct"] == pytest.approx(0.01) and x["mfe_bar"] == 1
    assert x["mae_pct"] == pytest.approx(0.01)
    assert x["realized_pct"] == pytest.approx(-0.01)
    assert x["giveback_pct"] == pytest.approx(0.02)


def test_short_with_mfe_on_the_exit_bar():
    # exit at the close of bar 2 (98.00, filled 98.02)
    x = run_excursions(
        trade(-1, 2, 9_802),
        high=[10_000, 10_080, 10_010],
        low=[10_000, 9_950, 9_700],
        close=[10_000, 10_000, 9_800],
    )
    assert x["mfe_pct"] == pytest.approx(0.03) and x["mfe_bar"] == 2
    assert x["mae_pct"] == pytest.approx(0.008)
    assert x["realized_pct"] == pytest.approx(0.02)
    assert x["giveback_pct"] == pytest.approx(0.01)


def test_open_trade_is_measured_to_the_last_bar():
    x = run_excursions(
        trade(1, None, None),
        high=[10_000, 10_200],
        low=[10_000, 9_990],
        close=[10_000, 10_100],
    )
    assert x["realized_pct"] == pytest.approx(0.01) and x["bars_held"] == 1


def test_write_run_exports_trades_enriched(tmp_path):
    params = {"start": "2025-01-03T00:00:00Z", "end": "2025-02-20T00:00:00Z"}
    result = Backtest(random_walk(1500, 7), EmaVwap, BrokerConfig(), params).run()
    folder = write_run(result, tmp_path, "case", "", {})
    enriched = pd.read_csv(folder / "trades_enriched.csv")
    trades = pd.read_csv(folder / "trades.csv")
    assert list(enriched["number"]) == list(trades["number"])
    for column in ("atr_pct", "crosses_24", "vol_ratio_7d", "mfe_pct", "giveback_pct", "mfe_bar"):
        assert column in enriched
