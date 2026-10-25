"""NY 4H Range Re-entry (BTCUSDT 5m): direct port of the Pine v6 script with the same inputs.

Per bar, in the script's order (process_orders_on_close = true):
1. New NY day (the day of month of the bar's open time changes): range and pending breakout are
   deleted. An open trade is not touched.
2. Range: high and low of the bars whose NY open time is inside range_session ("0000-0400" is
   00:00 to 03:55). The session is wall time, so the spring-forward day has 36 five-minute bars
   and the fall-back day 60. The first bar after the session makes the range ready.
3. Midnight exit: on the last bar of the NY day (its close time falls on the next NY day), an
   open trade is closed at the close by midnight_exit: "Off", "Close all", "Close only in
   profit" or "Close only in loss" (by broker.open_profit at that close). When it is not
   "Off", no entry opens on that bar. Without the 23:55 bar (a gap) there is no last bar and no
   midnight exit that day, as in the script.
4. Setup, only when flat before step 3 (strategy.close_all fills after the script ran, so the
   script still sees the position on that bar): a close below the range low starts a downside
   breakout, above the high an upside one. The breakout tracks its extreme (lowest low, highest
   high) through the entry bar. The first close back inside opens a long (after a downside
   breakout) or a short at that close; the stop is the extreme minus / plus sl_buffer_pct, the
   target rr times the risk from the entry ("From entry") or from the range edge ("From range
   boundary", skipped when the target is on the wrong side of the entry). A close straight
   through the range ("Enter in trend direction") opens a trade that way with thru_factor times
   the original risk, only with "From entry"; "Treat as opposite breakout" starts a breakout on
   the other side. Either way the old breakout is reset, also when no trade opens.

Stop and target are one bracket (Broker.exit_bracket), active from the next bar. Pine computes
the levels as floats; they become ticks by rounding to the nearest tick, ties up
(math.round_to_mintick). Limit fills get no slippage.

Range-gap rule (not in the script): a day whose range session misses any candle builds no range
and does not trade. The decision is made at the first bar after the session, from the bars seen
so far. counters["skipped_days"] counts the days of the run window (session close inside
[start, end)) with a missing range candle, also days without any candle.

Weekends (NY day) build no range when include_weekends is false. Only bars whose close time is
inside [start, end) can enter; an open position is closed with "Test end" on the first bar that
closes at or after end.
"""

from decimal import Decimal

import numpy as np
import pandas as pd

from real_edge_backtest.engine.sizing import size
from real_edge_backtest.engine.strategy import Strategy
from real_edge_backtest.indicators import pine_round

LONG, SHORT = 1, -1
TZ = "America/New_York"
TP_MODES = ("From entry", "From range boundary")
THRU_MODES = ("Enter in trend direction", "Treat as opposite breakout")
MIDNIGHT_MODES = ("Off", "Close all", "Close only in profit", "Close only in loss")
ONE_DAY = np.int64(86_400_000_000_000)


def _utc(value: str) -> pd.Timestamp:
    ts = pd.Timestamp(value)
    return ts.tz_localize("UTC") if ts.tzinfo is None else ts.tz_convert("UTC")


def parse_session(session: str) -> tuple[int, int]:
    """'HHMM-HHMM' as minutes of the day, start inclusive, end exclusive, within one day."""
    try:
        start, end = session.split("-")
        a = int(start[:2]) * 60 + int(start[2:])
        b = int(end[:2]) * 60 + int(end[2:])
    except ValueError:
        raise ValueError(f"range_session must be HHMM-HHMM, got {session!r}") from None
    if len(start) != 4 or len(end) != 4 or not 0 <= a < b <= 1440:
        raise ValueError(f"range_session must be HHMM-HHMM inside one day, got {session!r}")
    return a, b


def ny_clock(times: pd.Series | pd.DatetimeIndex) -> tuple[np.ndarray, np.ndarray]:
    """(NY day number since 1970-01-01, NY minute of the day) of UTC times."""
    local = pd.DatetimeIndex(times).as_unit("ns").tz_convert(TZ).tz_localize(None)
    ns = local.asi8
    days = ns // ONE_DAY
    minutes = (ns - days * ONE_DAY) // 60_000_000_000
    return days, minutes


def session_mask(
    days: np.ndarray, minutes: np.ndarray, session: tuple[int, int], weekends: bool
) -> np.ndarray:
    """Open time inside the session on an allowed NY weekday (1970-01-01 was a Thursday)."""
    inside = (minutes >= session[0]) & (minutes < session[1])
    if not weekends:
        inside &= (days + 3) % 7 < 5
    return inside


class NyRange(Strategy):
    params = {
        "range_session": "0000-0400",
        "include_weekends": True,
        "sl_buffer_pct": 0.1,
        "rr": 2.0,
        "tp_mode": "From entry",
        "thru_mode": "Enter in trend direction",
        "thru_factor": 0.5,
        "midnight_exit": "Close all",
        "position_pct": 95,
        "sizing_slip_ticks": 2,
        "fee_reserve_pct": 0.05,
        "start": "2020-01-01T00:00:00Z",
        "end": "2099-01-01T00:00:00Z",
    }

    def init(self) -> None:
        p = self.p
        for key, options in (
            ("tp_mode", TP_MODES),
            ("thru_mode", THRU_MODES),
            ("midnight_exit", MIDNIGHT_MODES),
        ):
            if p[key] not in options:
                raise ValueError(f"{key} must be one of {options}, got {p[key]!r}")
        if p["sl_buffer_pct"] < 0 or p["rr"] <= 0 or not 0 < p["thru_factor"] <= 1:
            raise ValueError("need sl_buffer_pct >= 0, rr > 0 and 0 < thru_factor <= 1")
        self.start = _utc(p["start"])
        self.end = _utc(p["end"])
        if self.start >= self.end:
            raise ValueError("start must precede end")
        session = parse_session(p["range_session"])
        weekends = bool(p["include_weekends"])

        days, minutes = ny_clock(self.time)
        close_days, _ = ny_clock(self.time_close)
        dom = pd.DatetimeIndex(self.time).tz_convert(TZ).day.to_numpy()
        self.new_day = np.concatenate(([False], dom[1:] != dom[:-1]))
        self.last_bar = close_days != days
        self.in_session = session_mask(days, minutes, session, weekends)
        self.day = days
        self.time_close_ns = pd.DatetimeIndex(self.time_close).as_unit("ns").asi8
        self.start_ns, self.end_ns = self.start.value, self.end.value

        self.expected = {}
        self.counters["skipped_days"] = 0
        if len(self.data):
            interval = self.time_close.iloc[0] - self.time.iloc[0]
            self.expected = self._calendar(days, session, weekends, interval)

        cfg = self.broker.config
        self.mintick = float(cfg.tick_size)
        self.position_pct = Decimal(str(p["position_pct"]))
        self.fee_reserve_pct = Decimal(str(p["fee_reserve_pct"]))
        self.counters["sizing_capped"] = 0
        self.counters["degenerate_brackets"] = 0

        # Script state ("var" variables)
        self.r_high = self.r_low = np.nan
        self.range_ready = False
        self.brk = 0
        self.ext = np.nan
        self.range_day = -1
        self.range_bars = 0
        self.range_broken = False  # the range-gap rule skipped this day

    def _calendar(
        self, days: np.ndarray, session: tuple[int, int], weekends: bool, interval: pd.Timedelta
    ) -> dict[int, int]:
        """Range bars each NY day should have, from a gap-free grid of bar open times. Counts
        counters["skipped_days"] from the whole dataset (a statistic; trading decides causally
        in next())."""
        first = pd.Timestamp(int(days[0]) * ONE_DAY).tz_localize(TZ)
        last = pd.Timestamp((int(days[-1]) + 1) * ONE_DAY).tz_localize(TZ)
        grid = pd.date_range(first.tz_convert("UTC"), last.tz_convert("UTC"), freq=interval)
        grid = grid[:-1].as_unit("ns")
        g_days, g_minutes = ny_clock(grid)
        g_in = session_mask(g_days, g_minutes, session, weekends)
        slots = pd.DataFrame({"day": g_days[g_in], "close": grid.asi8[g_in] + interval.value})
        per_day = slots.groupby("day")["close"].agg(["size", "max"])
        have = pd.Series(days[self.in_session]).value_counts()
        per_day["have"] = have.reindex(per_day.index, fill_value=0)
        last_close = self.time_close_ns[-1]
        counted = per_day[
            (per_day["max"] >= self.start.value)
            & (per_day["max"] < self.end.value)
            & (per_day["max"] <= last_close)
        ]
        self.counters["skipped_days"] = int((counted["have"] < counted["size"]).sum())
        return {int(day): int(n) for day, n in per_day["size"].items()}

    def _mark_capped(self, capped: bool) -> None:
        if capped and self.broker.open_trade is not None:
            self.broker.open_trade.sizing_capped = True
            self.counters["sizing_capped"] += 1

    def next(self) -> None:
        i, broker, p = self.i, self.broker, self.p
        time_close = self.time_close_ns[i]
        if time_close >= self.end_ns:
            if broker.position != 0:
                broker.close("Test end")
            return

        if self.new_day[i]:
            self.r_high = self.r_low = np.nan
            self.range_ready = False
            self.brk = 0
            self.ext = np.nan

        high, low, close = self.high[i], self.low[i], self.close[i]
        if self.in_session[i]:
            if self.range_day != self.day[i]:
                self.range_day, self.range_bars, self.range_broken = self.day[i], 0, False
            self.range_bars += 1
            self.r_high = high if np.isnan(self.r_high) else max(self.r_high, high)
            self.r_low = low if np.isnan(self.r_low) else min(self.r_low, low)
            self.range_ready = False
        elif not np.isnan(self.r_high) and not self.range_ready and not self.range_broken:
            if self.range_bars < self.expected.get(self.range_day, 0):
                self.range_broken = True
            else:
                self.range_ready = True

        flat = broker.position == 0
        mode = p["midnight_exit"]
        if self.last_bar[i] and not flat and mode != "Off":
            profit = broker.open_profit(broker.bar.close)
            if (
                mode == "Close all"
                or (mode == "Close only in profit" and profit > 0)
                or (mode == "Close only in loss" and profit < 0)
            ):
                broker.close("Midnight exit")
        allow = not (self.last_bar[i] and mode != "Off") and time_close >= self.start_ns

        if not (self.range_ready and flat):
            return
        if self.brk == 0:
            if close < self.r_low:
                self.brk, self.ext = -1, low
            elif close > self.r_high:
                self.brk, self.ext = 1, high
        elif self.brk == -1:
            self.ext = min(self.ext, low)
            if close > self.r_high:
                self._through(LONG, close, allow)
            elif close > self.r_low:
                self._reentry(LONG, close, allow)
        else:
            self.ext = max(self.ext, high)
            if close < self.r_low:
                self._through(SHORT, close, allow)
            elif close < self.r_high:
                self._reentry(SHORT, close, allow)

    def _through(self, side: int, close: float, allow: bool) -> None:
        """A close straight through the range against the pending breakout."""
        p = self.p
        if p["thru_mode"] == "Treat as opposite breakout":
            self.brk = side
            self.ext = self.high[self.i] if side == LONG else self.low[self.i]
            return
        if p["tp_mode"] == "From entry" and allow:
            buf = p["sl_buffer_pct"] / 100
            if side == LONG:
                orig_sl = self.ext * (1 - buf)
                risk = p["thru_factor"] * (close - orig_sl)
                sl, tp = close - risk, close + p["rr"] * risk
            else:
                orig_sl = self.ext * (1 + buf)
                risk = p["thru_factor"] * (orig_sl - close)
                sl, tp = close + risk, close - p["rr"] * risk
            self._enter(side, sl, tp, "Long thru" if side == LONG else "Short thru")
        self.brk, self.ext = 0, np.nan

    def _reentry(self, side: int, close: float, allow: bool) -> None:
        """The first close back inside the range after a breakout."""
        p = self.p
        buf, rr = p["sl_buffer_pct"] / 100, p["rr"]
        from_entry = p["tp_mode"] == "From entry"
        if side == LONG:
            sl = self.ext * (1 - buf)
            risk = close - sl
            tp = close + rr * risk if from_entry else self.r_low + rr * (self.r_low - sl)
            ok = tp > close
        else:
            sl = self.ext * (1 + buf)
            risk = sl - close
            tp = close - rr * risk if from_entry else self.r_high - rr * (sl - self.r_high)
            ok = tp < close
        if ok and allow:
            self._enter(side, sl, tp, "Long" if side == LONG else "Short")
        self.brk, self.ext = 0, np.nan

    def _ticks(self, level: float) -> int:
        """A Pine price level as ticks: nearest tick, ties up (math.round_to_mintick)."""
        return pine_round(level / self.mintick)

    def _enter(self, side: int, sl: float, tp: float, comment: str) -> None:
        """Market entry at this close with the stop and target bracket."""
        p, broker = self.p, self.broker
        cfg = broker.config
        stop, limit = self._ticks(sl), self._ticks(tp)
        # After rounding, a tiny risk can leave the stop at or beyond the close.
        if (limit - stop) * side <= 0 or (broker.bar.close - stop) * side <= 0:
            self.counters["degenerate_brackets"] += 1
            return
        expected_fill = broker.bar.close + side * p["sizing_slip_ticks"]
        lots, capped = size(
            self.sizing,
            self.equity,
            self.position_pct,
            self.fee_reserve_pct,
            expected_fill * cfg.tick_size,
            cfg.point_value,
            cfg.lot_size,
            abs(expected_fill - stop) * cfg.tick_size,
        )
        if lots <= 0 or not broker.entry(side, lots, comment):
            return
        self._mark_capped(capped)
        name = "Long exit" if side == LONG else "Short exit"
        broker.exit_bracket(f"{name} SL", stop, f"{name} TP", limit, name)
