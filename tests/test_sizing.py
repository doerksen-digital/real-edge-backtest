"""Sizing modes with exact numbers: percent_equity, fixed_risk, fixed_notional and the cap."""

from decimal import Decimal

import numpy as np
import pytest

from conftest import make_candles
from real_edge_backtest.engine import Backtest, BrokerConfig, load_config
from real_edge_backtest.engine.results import trades_frame
from real_edge_backtest.engine.sizing import SizingConfig, position_lots, size
from real_edge_backtest.strategies.ema_vwap import EmaVwap

D = Decimal
COMMON = {
    "equity": D("10000"),
    "position_pct": D("100"),
    "fee_reserve_pct": D("0.05"),
    "expected_fill": D("50000"),
    "point_value": D("1"),
    "lot_size": D("0.00001"),
}
# 100% of 10,000 with the fee reserve at 50,000: floor(10000 / 1.0005 / 50000 / 0.00001)
CAP = 19_990


def test_cap_value():
    assert position_lots(**COMMON) == CAP


def test_percent_equity_is_the_existing_rule():
    assert size(SizingConfig(), **COMMON, stop_distance=D(0)) == (CAP, False)
    half = {**COMMON, "position_pct": D("50")}
    assert size(SizingConfig(), **half, stop_distance=D(0)) == (position_lots(**half), False)


def test_fixed_risk():
    sizing = SizingConfig(mode="fixed_risk", risk_pct=D("1"))
    # risk 100 USD, stop 1,000.00 away: 100 / (1000 * 0.00001) = 10,000 lots = 0.1 BTC
    assert size(sizing, **COMMON, stop_distance=D("1000")) == (10_000, False)


def test_fixed_risk_is_capped_at_full_equity():
    sizing = SizingConfig(mode="fixed_risk", risk_pct=D("1"))
    # stop 400.00 away would need 25,000 lots (12,500 USD) > equity
    assert size(sizing, **COMMON, stop_distance=D("400")) == (CAP, True)


def test_fixed_risk_needs_a_stop():
    with pytest.raises(ValueError, match="needs a stop"):
        size(SizingConfig(mode="fixed_risk"), **COMMON, stop_distance=D(0))


def test_fixed_notional():
    sizing = SizingConfig(mode="fixed_notional", notional_usd=D("1000"))
    # 1,000 / 50,000 = 0.02 BTC = 2,000 lots
    assert size(sizing, **COMMON, stop_distance=D(0)) == (2_000, False)


def test_fixed_notional_is_capped_at_available_equity():
    sizing = SizingConfig(mode="fixed_notional", notional_usd=D("20000"))
    assert size(sizing, **COMMON, stop_distance=D(0)) == (CAP, True)


def test_unknown_mode_is_rejected():
    with pytest.raises(ValueError, match="sizing mode"):
        SizingConfig(mode="kelly")


class Forced(EmaVwap):
    """One long cross at bar 30, ATR forced to 5.00 (stop 2 x 5.00 = 1,000 ticks)."""

    def init(self) -> None:
        super().init()
        n = len(self.close)
        self.ema = np.zeros(n)
        self.vwap = np.zeros(n)
        self.atr = np.full(n, 5.0)
        self.cross_up = np.arange(n) == 30
        self.cross_down = np.zeros(n, dtype=bool)
        self.daily_ema_prev = np.full(n, 100.0)
        self.daily_close_prev = np.full(n, 100.0)


def run(sizing: SizingConfig):
    prices = [100.0] * 40
    candles = make_candles(prices, prices, prices, prices)
    params = {"start": "2025-01-01T00:00:00Z"}
    return Backtest(candles, Forced, BrokerConfig(), params, sizing=sizing).run()


def test_fixed_risk_in_a_run_and_capped_flag():
    # Entry 100.02, stop 10.00 away. 1% of 10,000 = 100 USD / 10.00 = 10 BTC = 1,000,000 lots,
    # notional 1,000.20 USD: not capped.
    result = run(SizingConfig(mode="fixed_risk", risk_pct=D("1")))
    assert result.trades[0].lots == 1_000_000
    assert not result.trades[0].sizing_capped
    # 20% risk would need 200 BTC (20,004 USD): capped at 100% of equity.
    result = run(SizingConfig(mode="fixed_risk", risk_pct=D("20")))
    trade = result.trades[0]
    assert trade.sizing_capped and result.counters["sizing_capped"] == 1
    assert trade.lots == position_lots(
        D("10000"), D("100"), D("0.05"), D("100.02"), D("1"), D("0.00001")
    )
    assert bool(trades_frame(result).loc[0, "sizing_capped"])


def test_sizing_section_is_read_from_config(tmp_path):
    path = tmp_path / "c.toml"
    path.write_text(
        'name = "x"\n[data]\nsymbol = "BTCUSDT"\ninterval = "1h"\n[strategy]\nname = "ema_vwap"\n'
        '[sizing]\nmode = "fixed_risk"\nrisk_pct = "0.5"\n',
        encoding="utf-8",
    )
    assert load_config(path).sizing == SizingConfig(mode="fixed_risk", risk_pct=D("0.5"))
