"""NY 4H Range Re-entry on hand-made 5m candles. Prices in USD on the 0.01 tick grid, commission
0.05%, slippage 2 ticks. Candles are flat at 100.00 unless set; the range bar at 01:00 NY makes
the range 99.00 to 101.00."""

from decimal import Decimal

import pandas as pd
import pytest

from real_edge_backtest.engine import Backtest, Broker, BrokerConfig
from real_edge_backtest.engine.sizing import SizingConfig
from real_edge_backtest.strategies.ny_range import TZ, NyRange

FIVE = pd.Timedelta(minutes=5)
WINTER = "2026-01-14"  # Wednesday, EST
BAR = tuple[float, float, float, float]


class Days:
    """5m candles over whole NY days, every price at 100.00."""

    def __init__(self, first: str = WINTER, days: int = 1, range_bar: bool = True) -> None:
        start = pd.Timestamp(first, tz=TZ)
        end = start + pd.DateOffset(days=days)
        times = pd.date_range(
            start.tz_convert("UTC"), end.tz_convert("UTC"), freq="5min", inclusive="left"
        )
        self.first = first
        self.frame = pd.DataFrame({"open_time": times})
        for column in ("open", "high", "low", "close", "volume"):
            self.frame[column] = 100.0
        if range_bar:
            self.set("01:00", (100, 101, 99, 100))

    def index(self, when: str, day: str | None = None) -> int:
        stamp = pd.Timestamp(f"{day or self.first} {when}", tz=TZ).tz_convert("UTC")
        return int(self.frame.index[self.frame["open_time"] == stamp][0])

    def set(self, when: str, bar: BAR, day: str | None = None) -> "Days":
        i = self.index(when, day)
        self.frame.loc[i, ["open", "high", "low", "close"]] = [float(v) for v in bar]
        return self

    def drop(self, when: str) -> "Days":
        self.frame = self.frame.drop(index=self.index(when)).reset_index(drop=True)
        return self

    def utc(self, when: str, day: str | None = None) -> pd.Timestamp:
        return pd.Timestamp(f"{day or self.first} {when}", tz=TZ).tz_convert("UTC")


def run(days: Days, model: str = "pessimistic", cls=NyRange, **params):
    params = {"start": "2020-01-01T00:00:00Z", **params}
    return Backtest(days.frame, cls, BrokerConfig(fill_model=model), params, interval=FIVE).run()


def strategy(days: Days, **params) -> NyRange:
    data = days.frame.assign(time_close=days.frame["open_time"] + FIVE)
    s = NyRange(data, Broker(BrokerConfig()), params)
    s.init()
    return s


class Recorder(NyRange):
    """NyRange that keeps its state after every bar."""

    log: list = []

    def next(self) -> None:
        super().next()
        Recorder.log.append((self.r_high, self.r_low, self.range_ready, self.brk, self.ext))


def long_setup(days: Days, day: str | None = None) -> Days:
    """Close below the range at 05:00 (low 98.40), a lower low at 05:05 (98.00), back inside at
    the 05:10 close of 99.50 with a wick to 97.90. Long at 99.52, stop 97.90 * 0.999 = 97.8021
    -> 97.80, target 99.50 + 2 * 1.6979 = 102.8958 -> 102.90."""
    days.set("05:00", (100, 100, 98.40, 98.50), day)
    days.set("05:05", (98.50, 98.60, 98.00, 98.80), day)
    return days.set("05:10", (98.80, 99.60, 97.90, 99.50), day)


def short_setup(days: Days) -> Days:
    """Mirror: close above at 05:00 (high 101.60), higher high 102.00, back inside at the 05:10
    close of 100.50 with a wick to 102.10. Short at 100.48, stop 102.10 * 1.001 = 102.2021 ->
    102.20, target 100.50 - 2 * 1.7021 = 97.0958 -> 97.10."""
    days.set("05:00", (100, 101.60, 100, 101.50))
    days.set("05:05", (101.50, 102.00, 101.40, 101.20))
    return days.set("05:10", (101.20, 102.10, 100.40, 100.50))


# Range window --------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("day", "bars"),
    [
        (WINTER, 48),
        ("2026-07-15", 48),  # EDT
        ("2026-03-08", 36),  # spring forward: 02:00 to 02:55 do not exist
        ("2026-11-01", 60),  # fall back: 01:00 to 01:55 happen twice
    ],
)
def test_range_window_has_the_wall_clock_bars(day, bars):
    days = Days(day, range_bar=False)
    s = strategy(days)
    local = days.frame["open_time"][s.in_session].dt.tz_convert(TZ)
    assert s.in_session.sum() == bars
    assert s.expected[int(s.day[0])] == bars
    assert (local.iloc[0].strftime("%H:%M"), local.iloc[-1].strftime("%H:%M")) == ("00:00", "03:55")


@pytest.mark.parametrize("day", [WINTER, "2026-07-15", "2026-03-08", "2026-11-01"])
def test_range_is_built_from_the_session_bars_only(day):
    days = Days(day, range_bar=False)
    days.set("00:00", (100, 102, 100, 100)).set("03:55", (100, 100, 97, 100))
    days.set("04:00", (100, 105, 95, 100))  # outside the window, closes inside
    Recorder.log = []
    run(days, cls=Recorder)
    assert Recorder.log[days.index("03:55")][:3] == (102, 97, False)
    assert Recorder.log[days.index("04:00")][:3] == (102, 97, True)


def test_a_missing_range_candle_skips_the_day():
    complete = long_setup(Days())
    assert len(run(complete).trades) == 1
    result = run(long_setup(Days()).drop("02:00"))
    assert result.trades == []
    assert result.counters["skipped_days"] == 1
    assert run(complete).counters["skipped_days"] == 0


def test_a_day_without_candles_counts_as_skipped():
    days = Days(days=3)
    gone = days.frame["open_time"].dt.tz_convert(TZ).dt.strftime("%Y-%m-%d") == "2026-01-15"
    days.frame = days.frame[~gone].reset_index(drop=True)
    assert run(days).counters["skipped_days"] == 1


def test_excluded_weekend_builds_no_range():
    saturday = "2026-01-17"
    assert len(run(long_setup(Days(saturday))).trades) == 1
    result = run(long_setup(Days(saturday)), include_weekends=False)
    assert result.trades == [] and result.counters["skipped_days"] == 0


# Re-entry --------------------------------------------------------------------------------------


@pytest.mark.parametrize("model", ["tradingview", "pessimistic"])
def test_downside_breakout_and_reentry_opens_a_long(model):
    days = long_setup(Days()).set("06:00", (100, 103, 100, 101))
    trade = run(days, model).trades[0]
    assert (trade.side, trade.entry_comment, trade.entry_price) == (1, "Long", 9_952)
    assert trade.entry_time == days.utc("05:10")
    assert (trade.exit_kind, trade.exit_price, trade.exit_comment) == ("limit", 10_290, "Long exit")


def test_long_stop_is_the_extreme_minus_the_buffer():
    days = long_setup(Days()).set("06:00", (100, 100, 97.70, 98))
    trade = run(days).trades[0]
    assert (trade.exit_kind, trade.exit_price) == ("stop", 9_778)  # 97.80 minus 2 ticks


@pytest.mark.parametrize("model", ["tradingview", "pessimistic"])
def test_upside_breakout_and_reentry_opens_a_short(model):
    days = short_setup(Days()).set("06:00", (100, 100, 97, 98))
    trade = run(days, model).trades[0]
    assert (trade.side, trade.entry_comment, trade.entry_price) == (-1, "Short", 10_048)
    assert (trade.exit_kind, trade.exit_price, trade.exit_comment) == ("limit", 9_710, "Short exit")
    stopped = run(short_setup(Days()).set("06:00", (100, 102.30, 100, 101))).trades[0]
    assert (stopped.exit_kind, stopped.exit_price) == ("stop", 10_222)


def test_extreme_follows_new_lows_including_the_entry_wick():
    Recorder.log = []
    days = long_setup(Days())
    run(days, cls=Recorder)
    assert Recorder.log[days.index("05:00")][3:] == (-1, 98.40)
    assert Recorder.log[days.index("05:05")][3:] == (-1, 98.00)
    # The 05:10 entry bar's wick (97.90) sets the stop: 97.80, so a low of 97.85 does not stop.
    trade = run(long_setup(Days()).set("06:00", (100, 100, 97.85, 98))).trades[0]
    assert trade.exit_comment == "Midnight exit"


def test_the_bar_that_closes_a_trade_can_start_a_new_breakout():
    days = long_setup(Days()).set("06:00", (100, 103, 98.40, 98.50))  # target, then below 99
    days.set("06:05", (98.50, 99.60, 98.30, 99.50))
    first, second = run(days).trades
    assert first.exit_kind == "limit" and first.exit_time == days.utc("06:00")
    assert (second.entry_time, second.side) == (days.utc("06:05"), 1)


# Through the range -----------------------------------------------------------------------------


def thru_long(days: Days) -> Days:
    """Downside breakout at 05:00 (low 98.40), then a close of 101.50 above the range with a low
    of 98.20. Original stop 98.20 * 0.999 = 98.1018, risk 0.5 * 3.3982 = 1.6991, stop 99.8009 ->
    99.80, target 101.50 + 3.3982 = 104.8982 -> 104.90."""
    days.set("05:00", (100, 100, 98.40, 98.50))
    return days.set("05:05", (98.50, 101.60, 98.20, 101.50))


def thru_short(days: Days) -> Days:
    """Mirror: upside breakout (high 101.60), then a close of 98.50 with a high of 101.80.
    Original stop 101.9018, risk 1.7009, stop 100.2009 -> 100.20, target 95.0982 -> 95.10."""
    days.set("05:00", (100, 101.60, 100, 101.50))
    return days.set("05:05", (101.50, 101.80, 98.40, 98.50))


def test_through_the_range_long_in_trend_direction_has_the_reduced_stop():
    trade = run(thru_long(Days()).set("06:00", (101, 105, 101, 104))).trades[0]
    assert (trade.side, trade.entry_comment, trade.entry_price) == (1, "Long thru", 10_152)
    assert (trade.exit_kind, trade.exit_price) == ("limit", 10_490)
    stopped = run(thru_long(Days()).set("06:00", (101, 101, 99.70, 100))).trades[0]
    assert (stopped.exit_kind, stopped.exit_price) == ("stop", 9_978)


def test_through_the_range_short_in_trend_direction_has_the_reduced_stop():
    trade = run(thru_short(Days()).set("06:00", (98, 98, 95, 96))).trades[0]
    assert (trade.side, trade.entry_comment, trade.entry_price) == (-1, "Short thru", 9_848)
    assert (trade.exit_kind, trade.exit_price) == ("limit", 9_510)
    stopped = run(thru_short(Days()).set("06:00", (99, 100.30, 99, 100))).trades[0]
    assert (stopped.exit_kind, stopped.exit_price) == ("stop", 10_022)


def test_through_the_range_as_opposite_breakout_then_short():
    """After the downside breakout, the 101.50 close starts an upside breakout (extreme 101.60).
    The 05:10 close of 100.50 (high 101.70) is back inside: short, stop 101.70 * 1.001 =
    101.8017 -> 101.80, target 100.50 - 2 * 1.3017 = 97.8966 -> 97.90."""
    days = thru_long(Days()).set("05:10", (101.50, 101.70, 100.40, 100.50))
    days.set("06:00", (100, 100, 97, 98))
    trade = run(days, thru_mode="Treat as opposite breakout").trades[0]
    assert (trade.side, trade.entry_comment, trade.entry_time) == (-1, "Short", days.utc("05:10"))
    assert (trade.exit_kind, trade.exit_price) == ("limit", 9_790)


def test_through_the_range_as_opposite_breakout_then_long():
    """Mirror: the 98.50 close starts a downside breakout (extreme 98.40). The 05:10 close of
    99.50 (low 98.30) is back inside: long, stop 98.30 * 0.999 = 98.2017 -> 98.20, target
    99.50 + 2 * 1.2983 = 102.0966 -> 102.10."""
    days = thru_short(Days()).set("05:10", (98.50, 99.60, 98.30, 99.50))
    days.set("06:00", (100, 103, 100, 101))
    trade = run(days, thru_mode="Treat as opposite breakout").trades[0]
    assert (trade.side, trade.entry_comment, trade.entry_time) == (1, "Long", days.utc("05:10"))
    assert (trade.exit_kind, trade.exit_price) == ("limit", 10_210)


def test_through_the_range_with_tp_from_range_boundary_trades_nothing_and_resets():
    days = thru_long(Days()).set("05:10", (101.50, 101.70, 100.40, 100.50))
    assert run(days, tp_mode="From range boundary").trades == []


# TP from the range boundary ------------------------------------------------------------------


def test_tp_from_range_boundary():
    """Target 99.00 + 2 * (99.00 - 97.8021) = 101.3958 -> 101.40."""
    days = long_setup(Days()).set("06:00", (100, 101.50, 100, 101))
    trade = run(days, tp_mode="From range boundary").trades[0]
    assert (trade.exit_kind, trade.exit_price) == ("limit", 10_140)


def test_tp_from_range_boundary_on_the_wrong_side_skips_the_trade():
    """rr 0.2: target 99.00 + 0.2 * 1.1979 = 99.2396, below the 99.50 entry. Skipped, and the
    breakout is reset, so the 05:15 close inside does not enter either."""
    days = long_setup(Days()).set("05:15", (99.50, 99.60, 99.40, 99.50))
    assert run(days, tp_mode="From range boundary", rr=0.2).trades == []


# Midnight exit -------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("mode", "close", "closed"),
    [
        ("Off", 100.50, False),
        ("Close all", 100.50, True),
        ("Close all", 99.00, True),
        ("Close only in profit", 100.50, True),
        ("Close only in profit", 99.00, False),
        ("Close only in loss", 100.50, False),
        ("Close only in loss", 99.00, True),
    ],
)
def test_midnight_exit(mode, close, closed):
    days = long_setup(Days(days=2))
    days.set("23:55", (close, close, close, close))
    trade = run(days, midnight_exit=mode).trades[0]
    if closed:
        assert (trade.exit_comment, trade.exit_time) == ("Midnight exit", days.utc("23:55"))
        assert trade.exit_price == round(close * 100) - 2
    else:
        assert trade.exit_time != days.utc("23:55")


@pytest.mark.parametrize(("mode", "trades"), [("Close all", 0), ("Off", 1)])
def test_no_entry_on_the_last_bar_when_the_midnight_exit_is_on(mode, trades):
    days = Days(days=2)
    days.set("23:45", (100, 100, 98.40, 98.50)).set("23:50", (98.50, 98.60, 98.40, 98.50))
    days.set("23:55", (98.50, 99.60, 98.30, 99.50))
    result = run(days, midnight_exit=mode)
    assert len(result.trades) == trades
    if trades:
        assert result.trades[0].entry_time == days.utc("23:55")


def test_day_reset_does_not_touch_an_open_trade():
    days = long_setup(Days(days=2))
    second = "2026-01-15"
    days.set("01:00", (100, 101, 99, 100), second)
    long_setup(days, second)  # a new setup while the trade is open: ignored
    days.set("06:00", (100, 103, 100, 101), second)
    trades = run(days, midnight_exit="Off").trades
    assert len(trades) == 1
    assert trades[0].entry_time == days.utc("05:10")
    assert (trades[0].exit_kind, trades[0].exit_price) == ("limit", 10_290)
    assert trades[0].exit_time == days.utc("06:00", second)


# Window and sizing ---------------------------------------------------------------------------


def test_no_entry_before_start():
    days = long_setup(Days())
    # Start is compared with the close time: the 05:10 entry bar closes at 05:15.
    assert run(days, start=str(days.utc("05:20"))).trades == []
    assert len(run(days, start=str(days.utc("05:15"))).trades) == 1


def test_open_trade_is_closed_at_test_end():
    days = long_setup(Days())
    trade = run(days, end=str(days.utc("07:00"))).trades[0]
    assert (trade.exit_comment, trade.exit_time) == ("Test end", days.utc("06:55"))


def test_unknown_mode_is_rejected():
    with pytest.raises(ValueError, match="midnight_exit"):
        run(Days(), midnight_exit="Close sometimes")


def test_percent_equity_uses_95_percent_of_equity():
    trade = run(long_setup(Days())).trades[0]
    # floor(10,000 * 0.95 / 1.0005 / 99.52 / 0.00001), expected fill 99.50 + 2 ticks
    assert trade.lots == 9_541_049


def test_fixed_risk_uses_the_distance_from_the_expected_fill_to_the_stop():
    days = long_setup(Days())
    data = days.frame
    sizing = SizingConfig(mode="fixed_risk", risk_pct=Decimal("1"))
    params = {"start": "2020-01-01T00:00:00Z"}
    result = Backtest(data, NyRange, BrokerConfig(), params, interval=FIVE, sizing=sizing).run()
    # 1% of 10,000 over (99.52 - 97.80) per BTC: floor(100 / 1.72 / 0.00001)
    assert result.trades[0].lots == 5_813_953
