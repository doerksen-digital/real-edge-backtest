"""EMA 9 / Rolling VWAP Cross v1: direct port of the Pine v6 script with the same inputs.

Long on ta.crossover(EMA, VWAP), short on ta.crossunder. An opposite cross reverses the position
in one order. A 2 x ATR(14) stop, frozen at entry, can fill intrabar; after it the strategy is
flat until the next cross. Optional daily trend filter: longs only if the previous completed
daily close is above the previous completed daily EMA, shorts only if below; a blocked cross
still closes the open trade. Only bars whose close time is inside [start, end) can trade, and an
open position is closed with "Test end" on the first bar that closes at or after end.
"""

import math
from decimal import Decimal
from fractions import Fraction

import pandas as pd

from real_edge_backtest.data.daily import daily_candles, previous_day_values
from real_edge_backtest.engine.strategy import Strategy
from real_edge_backtest.indicators import atr, crossover, crossunder, ema, pine_round, rolling_vwap

LONG, SHORT = 1, -1


def position_lots(
    equity: Decimal,
    position_pct: Decimal,
    fee_reserve_pct: Decimal,
    expected_fill: Decimal,
    point_value: Decimal,
    lot_size: Decimal,
) -> int:
    """floor(equity * pct/100 / (1 + fee/100) / (expected_fill * pointvalue) / lot) in lots.

    Computed with exact fractions, so a quotient that is an exact integer never floors to the
    integer below because of binary rounding.
    """
    equity = max(Decimal(0), equity)
    if expected_fill <= 0 or lot_size <= 0:
        return 0
    notional = (
        Fraction(equity) * Fraction(position_pct) / 100 / (1 + Fraction(fee_reserve_pct) / 100)
    )
    return math.floor(
        notional / (Fraction(expected_fill) * Fraction(point_value)) / Fraction(lot_size)
    )


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

        cfg = self.broker.config
        self.mintick = float(cfg.tick_size)
        self.position_pct = Decimal(str(p["position_pct"]))
        self.fee_reserve_pct = Decimal(str(p["fee_reserve_pct"]))
        self.time_close_list = list(self.time_close)

    def next(self) -> None:
        i, p, broker = self.i, self.p, self.broker
        time_close = self.time_close_list[i]
        in_range = self.start <= time_close < self.end

        if time_close >= self.end:
            if broker.position != 0:
                broker.cancel("L-Stop")
                broker.cancel("S-Stop")
                broker.close("Test end")
            return

        ready = self.valid(self.ema[i], self.vwap[i], self.atr[i]) and self.atr[i] > 0
        up, down = bool(self.cross_up[i]), bool(self.cross_down[i])
        if not (in_range and ready and (up or down)):
            return

        trend_known = self.valid(self.daily_ema_prev[i], self.daily_close_prev[i])
        trend_up = trend_known and self.daily_close_prev[i] > self.daily_ema_prev[i]
        trend_down = trend_known and self.daily_close_prev[i] < self.daily_ema_prev[i]
        long_allowed = p["direction"] != "Short only" and (not p["use_trend"] or trend_up)
        short_allowed = p["direction"] != "Long only" and (not p["use_trend"] or trend_down)

        side = LONG if up else SHORT
        cfg = broker.config
        expected_fill = (broker.bar.close + side * p["sizing_slip_ticks"]) * cfg.tick_size
        lots = position_lots(
            self.equity,
            self.position_pct,
            self.fee_reserve_pct,
            expected_fill,
            cfg.point_value,
            cfg.lot_size,
        )
        stop_ticks = int(max(1, pine_round(p["stop_atr"] * self.atr[i] / self.mintick)))

        if up:
            if long_allowed and lots > 0:
                broker.cancel("S-Stop")
                broker.entry(LONG, lots, "EMA above VWAP")
                if p["stop_atr"] > 0:
                    broker.exit_stop("L-Stop", stop_ticks, "ATR stop")
            elif broker.position < 0:
                broker.cancel("S-Stop")
                broker.close("Cross up, exit only")
        else:
            if short_allowed and lots > 0:
                broker.cancel("L-Stop")
                broker.entry(SHORT, lots, "EMA below VWAP")
                if p["stop_atr"] > 0:
                    broker.exit_stop("S-Stop", stop_ticks, "ATR stop")
            elif broker.position > 0:
                broker.cancel("L-Stop")
                broker.close("Cross down, exit only")
