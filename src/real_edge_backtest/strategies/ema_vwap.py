"""EMA 9 / Rolling VWAP Cross v1: direct port of the Pine v6 script with the same inputs.

Long on ta.crossover(EMA, VWAP), short on ta.crossunder. An opposite cross reverses the position
in one order. A 2 x ATR(14) stop, frozen at entry, can fill intrabar; after it the strategy is
flat until the next cross. No cross is acted on until EMA, VWAP, ATR and the previous
completed day's close and daily EMA all exist. Optional daily trend filter: longs only if the
previous completed daily close is above the previous completed daily EMA, shorts only if below;
a blocked cross still closes the open trade. Only bars whose close time is inside [start, end)
can trade, and an open position is closed with "Test end" on the first bar that closes at or
after end.

After a gap of at least min_gap_bars missing candles (Backtest setting), crosses are ignored
entirely until max(vwap_bars, atr_length, ema_length) contiguous candles exist again, so no
entry uses a VWAP window that spans the gap. An open trade keeps its stop meanwhile.

Optional plug-ins (strategies.plugins): entry filters act where the trend filter acts and may
defer an entry; exit rules run at each close with an open trade. Without them nothing changes.

Entry features (trades_enriched.csv, entry bar i, nothing after i):
- atr_pct: ATR / close
- dist_daily_ema_atr: (close - previous day's daily EMA) / ATR
- daily_ema_slope_pct: previous day's daily EMA / the day before's - 1
- sep_atr: (EMA - VWAP) / ATR; sep_atr_side: the same times the trade side
- crosses_24, crosses_48: EMA/VWAP crosses either way in the 24 or 48 bars before i
- vol_ratio_24, vol_ratio_7d: volume of bar i / mean volume of the 24 bars or of the bars of
  the 7 days before i
- hour_utc, weekday_utc (Monday 0): of the entry fill, the close time of bar i
Windows count bars, like the indicators; a value is na until the window has enough bars.
"""

from dataclasses import dataclass
from decimal import Decimal

import numpy as np
import pandas as pd

from real_edge_backtest.data.daily import daily_candles, previous_day_values
from real_edge_backtest.engine.sizing import size
from real_edge_backtest.engine.strategy import Strategy
from real_edge_backtest.indicators import atr, crossover, crossunder, ema, pine_round, rolling_vwap
from real_edge_backtest.strategies.plugins import ALLOW, CANCEL, Defer

LONG, SHORT = 1, -1


@dataclass(frozen=True)
class Pending:
    """A signal an entry filter deferred: side, filter index, bar of the cross, bars allowed."""

    side: int
    filter: int
    bar: int
    bars: int


def _utc(value: str) -> pd.Timestamp:
    ts = pd.Timestamp(value)
    return ts.tz_localize("UTC") if ts.tzinfo is None else ts.tz_convert("UTC")


class EmaVwap(Strategy):
    params = {
        "ema_length": 9,
        "vwap_bars": 24,
        "stop_atr": 2.0,
        "atr_length": 14,
        "use_trend": False,
        "trend_length": 200,
        "position_pct": 100,
        "sizing_slip_ticks": 2,
        "fee_reserve_pct": 0.05,
        "direction": "Both",
        "start": "2020-01-01T00:00:00Z",
        "end": "2099-01-01T00:00:00Z",
    }

    def init(self) -> None:
        p = self.p
        if p["direction"] not in ("Both", "Long only", "Short only"):
            raise ValueError(f"direction must be Both, Long only or Short only: {p['direction']}")
        self.start = _utc(p["start"])
        self.end = _utc(p["end"])
        if self.start >= self.end:
            raise ValueError("start must precede end")

        self.ema = ema(self.close, p["ema_length"])
        self.vwap = rolling_vwap(self.high, self.low, self.close, self.volume, p["vwap_bars"])
        self.cross_up = crossover(self.ema, self.vwap)
        self.cross_down = crossunder(self.ema, self.vwap)
        self.atr = atr(self.high, self.low, self.close, p["atr_length"])

        daily = daily_candles(self.data)
        daily_ema = ema(daily["close"].to_numpy(dtype=float), p["trend_length"])
        self.daily_ema_prev = previous_day_values(self.time, daily.index, daily_ema)
        self.daily_close_prev = previous_day_values(
            self.time, daily.index, daily["close"].to_numpy(dtype=float)
        )
        self.daily_ema_prev2 = previous_day_values(self.time, daily.index, daily_ema, lag=2)

        cfg = self.broker.config
        self.mintick = float(cfg.tick_size)
        self.position_pct = Decimal(str(p["position_pct"]))
        self.fee_reserve_pct = Decimal(str(p["fee_reserve_pct"]))
        self.time_close_list = list(self.time_close)
        self.min_contiguous = max(p["vwap_bars"], p["atr_length"], p["ema_length"])
        self.counters["ignored_after_gap"] = 0
        self.counters["sizing_capped"] = 0
        self.counters["deferred"] = 0
        self.counters["deferred_entered"] = 0
        self.counters["deferred_cancelled"] = 0
        self.pending: Pending | None = None
        if self.sizing.mode == "fixed_risk" and p["stop_atr"] <= 0:
            raise ValueError("fixed_risk sizing needs the ATR stop (stop_atr > 0)")

    def bar_columns(self) -> dict[str, np.ndarray]:
        return {"atr": self.atr}

    def _window_sums(self) -> dict[str, np.ndarray]:
        """Prefix sums for the bar windows of entry_features, built on first use (after init
        and after any test subclass replaced the cross arrays)."""
        if not hasattr(self, "_sums"):
            crosses = (np.asarray(self.cross_up) | np.asarray(self.cross_down)).astype(np.int64)
            self._sums = {
                "crosses": np.concatenate(([0], np.cumsum(crosses))),
                "volume": np.concatenate(([0.0], np.cumsum(self.volume))),
            }
            interval = self.time_close.iloc[0] - self.time.iloc[0]
            self._bars_7d = int(pd.Timedelta(days=7) / interval)
        return self._sums

    def _before(self, name: str, i: int, n: int) -> float:
        """Sum of `name` over the n bars before i, na if fewer than n exist."""
        s = self._window_sums()[name]
        return float(s[i] - s[i - n]) if i >= n else np.nan

    def entry_features(self, i: int, side: int) -> dict[str, float]:
        close, atr = self.close[i], self.atr[i]
        self._window_sums()
        bars_7d = self._bars_7d
        fill_time = self.time_close.iloc[i]
        sep = (self.ema[i] - self.vwap[i]) / atr
        return {
            "atr_pct": atr / close,
            "dist_daily_ema_atr": (close - self.daily_ema_prev[i]) / atr,
            "daily_ema_slope_pct": self.daily_ema_prev[i] / self.daily_ema_prev2[i] - 1,
            "sep_atr": sep,
            "sep_atr_side": sep * side,
            "crosses_24": self._before("crosses", i, 24),
            "crosses_48": self._before("crosses", i, 48),
            "vol_ratio_24": self.volume[i] / (self._before("volume", i, 24) / 24),
            "vol_ratio_7d": self.volume[i] / (self._before("volume", i, bars_7d) / bars_7d),
            "hour_utc": fill_time.hour,
            "weekday_utc": fill_time.weekday(),
        }

    def _mark_capped(self, capped: bool) -> None:
        if capped and self.broker.open_trade is not None:
            self.broker.open_trade.sizing_capped = True
            self.counters["sizing_capped"] += 1

    def next(self) -> None:
        i, broker = self.i, self.broker
        time_close = self.time_close_list[i]
        in_range = self.start <= time_close < self.end

        if time_close >= self.end:
            self.pending = None
            if broker.position != 0:
                broker.cancel("L-Stop")
                broker.cancel("S-Stop")
                broker.close("Test end")
            return

        if in_range and self.exits and broker.open_trade is not None:
            for rule in self.exits:
                rule.on_bar(self, i, broker.open_trade)
                if broker.open_trade is None:
                    break

        # No trade until every indicator, including the previous day's daily values, exists.
        ready = (
            self.valid(
                self.ema[i],
                self.vwap[i],
                self.atr[i],
                self.daily_ema_prev[i],
                self.daily_close_prev[i],
            )
            and self.atr[i] > 0
        )
        up, down = bool(self.cross_up[i]), bool(self.cross_down[i])
        gap_block = self.contiguous_bars[i] < self.min_contiguous
        if self.pending is not None:
            self._resolve_pending(i, up, down, not (in_range and ready) or gap_block)
        if not (in_range and ready and (up or down)):
            return
        if gap_block:
            self.counters["ignored_after_gap"] += 1
            return
        self._signal(i, LONG if up else SHORT)

    def _signal(self, i: int, side: int) -> None:
        """A cross at the close of bar i: enter, defer, or only close the opposite position."""
        p = self.p
        trend_up = self.daily_close_prev[i] > self.daily_ema_prev[i]
        trend_down = self.daily_close_prev[i] < self.daily_ema_prev[i]
        if side == LONG:
            allowed = p["direction"] != "Short only" and (not p["use_trend"] or trend_up)
        else:
            allowed = p["direction"] != "Long only" and (not p["use_trend"] or trend_down)
        decision = self._run_filters(0, i, side) if allowed else CANCEL
        if decision == ALLOW and self._enter(i, side):
            return
        broker = self.broker
        if side == LONG and broker.position < 0:
            broker.cancel("S-Stop")
            broker.close("Cross up, exit only")
        elif side == SHORT and broker.position > 0:
            broker.cancel("L-Stop")
            broker.close("Cross down, exit only")

    def _run_filters(self, first: int, i: int, side: int) -> str:
        """Ask the entry filters from index `first` on. A deferral becomes the pending signal."""
        for k in range(first, len(self.filters)):
            f = self.filters[k]
            answer = f.on_signal(self, i, side)
            if answer == ALLOW:
                continue
            if isinstance(answer, Defer):
                if not 1 <= answer.bars <= f.max_defer:
                    raise ValueError(
                        f"plug-in {f.name!r} deferred {answer.bars} bars, allowed 1 to "
                        f"{f.max_defer}"
                    )
                self.pending = Pending(side, k, i, answer.bars)
                self.counters["deferred"] += 1
            return CANCEL
        return ALLOW

    def _resolve_pending(self, i: int, up: bool, down: bool, blocked: bool) -> None:
        """Re-check a deferred signal at the close of bar i (see strategies.plugins)."""
        pending = self.pending
        if (pending.side == LONG and down) or (pending.side == SHORT and up) or blocked:
            self.pending = None
            self.counters["deferred_cancelled"] += 1
            return
        waited = i - pending.bar
        answer = self.filters[pending.filter].on_pending(self, i, pending.side, waited)
        if answer == ALLOW:
            self.pending = None
            if self._run_filters(pending.filter + 1, i, pending.side) == ALLOW and self._enter(
                i, pending.side
            ):
                self.counters["deferred_entered"] += 1
            return
        if answer == CANCEL or waited >= pending.bars:
            self.pending = None
            self.counters["deferred_cancelled"] += 1

    def _enter(self, i: int, side: int) -> bool:
        """Market entry at the close of bar i with the ATR stop. False if the size is 0 lots."""
        p, broker = self.p, self.broker
        cfg = broker.config
        expected_fill = (broker.bar.close + side * p["sizing_slip_ticks"]) * cfg.tick_size
        stop_ticks = int(max(1, pine_round(p["stop_atr"] * self.atr[i] / self.mintick)))
        lots, capped = size(
            self.sizing,
            self.equity,
            self.position_pct,
            self.fee_reserve_pct,
            expected_fill,
            cfg.point_value,
            cfg.lot_size,
            stop_ticks * cfg.tick_size if p["stop_atr"] > 0 else Decimal(0),
        )
        if lots <= 0:
            return False
        own, opposite = ("L-Stop", "S-Stop") if side == LONG else ("S-Stop", "L-Stop")
        broker.cancel(opposite)
        broker.entry(side, lots, "EMA above VWAP" if side == LONG else "EMA below VWAP")
        self._mark_capped(capped)
        if p["stop_atr"] > 0:
            broker.exit_stop(own, stop_ticks, "ATR stop")
        return True
