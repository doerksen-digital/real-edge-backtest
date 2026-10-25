"""Trade and equity metrics from a run folder (trades.csv, equity.csv, run.json).

Reads result files only, so any run folder can be analyzed without the engine. Every equity
based number uses the curve cut to the run window (window_equity); the full-dataset curve in
equity.csv is never used directly.

Definitions:
- closed trades only; profit factor = sum of winning net PnL / -sum of losing net PnL
- a trade belongs to the calendar year (UTC) and half of the window in which it exits; a bar
  belongs to the year of its open time
- time in market = share of window bars entered with an open position
- max drawdown = largest peak-to-trough fall, in money and in percent of the peak; the
  starting capital is the first peak
- buy and hold: one buy at the first window bar's open plus slippage, as many lots as the
  starting capital pays for including the commission, marked at every close, sold at the last
  window bar's close minus slippage, with the same commission
"""

import json
import math
from dataclasses import dataclass, field
from decimal import Decimal
from fractions import Fraction
from pathlib import Path
from typing import Any

import pandas as pd


@dataclass(frozen=True)
class Criteria:
    """Pass criteria, fixed in the run config ([criteria]) before the run."""

    min_profit_factor: float = 1.3
    min_trades: int = 30
    without_top_n: int = 5  # still positive without the N best trades
    top_n: tuple[int, ...] = (1, 3, 5)  # reported "PnL without top N" values

    @classmethod
    def from_dict(cls, raw: dict[str, Any] | None) -> "Criteria":
        raw = dict(raw or {})
        unknown = set(raw) - set(cls.__dataclass_fields__)
        if unknown:
            raise ValueError(f"unknown criteria: {sorted(unknown)}")
        if "top_n" in raw:
            raw["top_n"] = tuple(int(n) for n in raw["top_n"])
        return cls(**raw)


@dataclass
class Run:
    meta: dict[str, Any]
    trades: pd.DataFrame
    equity: pd.DataFrame
    folder: Path | None = None

    @property
    def start(self) -> pd.Timestamp:
        return _utc(self.meta["window"]["start"])

    @property
    def end(self) -> pd.Timestamp:
        return _utc(self.meta["window"]["end"])

    @property
    def initial_capital(self) -> float:
        return float(self.meta["broker"]["initial_capital"])


def _utc(value: str) -> pd.Timestamp:
    ts = pd.Timestamp(value)
    return ts.tz_localize("UTC") if ts.tzinfo is None else ts.tz_convert("UTC")


def load_run(folder: Path) -> Run:
    meta = json.loads((folder / "run.json").read_text(encoding="utf-8"))
    trades = pd.read_csv(folder / "trades.csv")
    for column in ("entry_time", "exit_time"):
        trades[column] = pd.to_datetime(trades[column], utc=True)
    equity = pd.read_csv(folder / "equity.csv")
    for column in ("open_time", "time_close"):
        equity[column] = pd.to_datetime(equity[column], utc=True)
    return Run(meta, trades, equity, folder)


# Window --------------------------------------------------------------------------------------


def window_equity(equity: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    """Bars of the run window: from the first bar closing at or after start through the first
    bar closing at or after end (the bar on which an open trade is closed with "Test end").
    Adds `held`: the bar was entered with an open position."""
    eq = equity.assign(held=equity["position"].shift(1, fill_value=0) != 0)
    after_end = eq.index[eq["time_close"] >= end]
    last = after_end[0] if len(after_end) else eq.index[-1]
    return eq[(eq["time_close"] >= start) & (eq.index <= last)].reset_index(drop=True)


# Trade statistics ----------------------------------------------------------------------------


def closed(trades: pd.DataFrame) -> pd.DataFrame:
    return trades[trades["exit_time"].notna()]


def trade_stats(trades: pd.DataFrame) -> dict[str, float]:
    pnl = closed(trades)["net_pnl"]
    wins, losses = pnl[pnl > 0], pnl[pnl < 0]
    gross_loss = -losses.sum()
    return {
        "trades": int(len(pnl)),
        "net_pnl": float(pnl.sum()),
        "profit_factor": float(wins.sum() / gross_loss) if gross_loss else math.inf,
        "expectancy": float(pnl.mean()) if len(pnl) else 0.0,
        "win_rate": float(len(wins) / len(pnl)) if len(pnl) else 0.0,
        "average_win": float(wins.mean()) if len(wins) else 0.0,
        "average_loss": float(losses.mean()) if len(losses) else 0.0,
    }


def pnl_without_top(trades: pd.DataFrame, n: int) -> float:
    """Net PnL after removing the n best winning trades."""
    pnl = closed(trades)["net_pnl"]
    top = pnl[pnl > 0].nlargest(n)
    return float(pnl.sum() - top.sum())


def by_year(trades: pd.DataFrame, window: pd.DataFrame, initial_capital: float) -> pd.DataFrame:
    """Trade stats per exit year plus the equity return of each calendar year in the window."""
    t = closed(trades)
    years = window["open_time"].dt.year  # the year a bar belongs to, like trade exits
    rows = []
    previous = initial_capital
    for year in sorted(years.unique()):
        last = float(window.loc[years == year, "equity"].iloc[-1])
        stats = trade_stats(t[t["exit_time"].dt.year == year])
        rows.append({"year": int(year), **stats, "return": last / previous - 1})
        previous = last
    return pd.DataFrame(rows)


def halves(trades: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp) -> list[dict]:
    """Trade stats for the first and second half of the window, split at its midpoint."""
    t = closed(trades)
    mid = start + (end - start) / 2
    first = t[t["exit_time"] < mid]
    second = t[t["exit_time"] >= mid]
    return [
        {"half": "first", "from": start, "to": mid, **trade_stats(first)},
        {"half": "second", "from": mid, "to": end, **trade_stats(second)},
    ]


# Equity statistics ---------------------------------------------------------------------------


def max_drawdown(values: pd.Series, initial: float) -> tuple[float, float]:
    """Largest peak-to-trough fall (money, fraction of the peak), starting from `initial`."""
    curve = pd.concat([pd.Series([initial]), values.reset_index(drop=True)], ignore_index=True)
    peak = curve.cummax()
    fall = peak - curve
    i = int(fall.idxmax())
    return float(fall.iloc[i]), float(fall.iloc[i] / peak.iloc[i]) if peak.iloc[i] else 0.0


def closed_trade_equity(trades: pd.DataFrame, initial: float) -> pd.Series:
    t = closed(trades).sort_values("exit_time")
    return initial + t["net_pnl"].cumsum()


def time_in_market(window: pd.DataFrame) -> float:
    return float(window["held"].mean()) if len(window) else 0.0


def buy_and_hold(window: pd.DataFrame, broker: dict[str, Any]) -> dict[str, Any]:
    """Buy and hold over the window with the run's capital, commission and slippage."""
    capital = Fraction(Decimal(broker["initial_capital"]))
    rate = Fraction(Decimal(broker["commission_pct"])) / 100
    tick = Fraction(Decimal(broker["tick_size"]))
    lot = Fraction(Decimal(broker["lot_size"]))
    point = Fraction(Decimal(broker["point_value"]))
    slip = broker["slippage_ticks"] * tick

    def price(value: float) -> Fraction:
        return Fraction(Decimal(str(value)))

    entry = price(window["open"].iloc[0]) + slip
    lots = math.floor(capital / (1 + rate) / (entry * point) / lot)
    qty = lots * lot * point
    cash = capital - qty * entry * (1 + rate)
    curve = [float(cash + qty * price(c)) for c in window["close"]]
    exit_price = price(window["close"].iloc[-1]) - slip
    final = cash + qty * exit_price * (1 - rate)
    curve[-1] = float(final)
    curve = pd.Series(curve, index=window["open_time"])
    dd, dd_pct = max_drawdown(curve, float(capital))
    return {
        "lots": lots,
        "entry_price": float(entry),
        "exit_price": float(exit_price),
        "final_equity": float(final),
        "return": float(final / capital - 1),
        "max_drawdown": dd,
        "max_drawdown_pct": dd_pct,
        "time_in_market": 1.0,
        "curve": curve,
    }


# Everything together -------------------------------------------------------------------------


@dataclass
class Check:
    name: str
    threshold: str
    value: str
    passed: bool | None  # None: comparison only, not a pass criterion


@dataclass
class Analysis:
    window: pd.DataFrame
    stats: dict[str, float]
    without_top: dict[int, float]
    years: pd.DataFrame
    halves: list[dict]
    time_in_market: float
    max_drawdown: tuple[float, float]
    closed_drawdown: tuple[float, float]
    total_return: float
    buy_and_hold: dict[str, Any]
    checks: list[Check] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return all(c.passed for c in self.checks if c.passed is not None)


def analyze(run: Run, trades: pd.DataFrame | None = None) -> Analysis:
    """All metrics of a run. `trades` replaces the run's trades (e.g. without gap trades);
    equity-based numbers always come from the run's own curve."""
    trades = run.trades if trades is None else trades
    criteria = Criteria.from_dict(run.meta.get("criteria"))
    capital = run.initial_capital
    window = window_equity(run.equity, run.start, run.end)
    stats = trade_stats(trades)
    without = {
        n: pnl_without_top(trades, n) for n in sorted({*criteria.top_n, criteria.without_top_n})
    }
    two = halves(trades, run.start, run.end)
    bh = buy_and_hold(window, run.meta["broker"])
    analysis = Analysis(
        window=window,
        stats=stats,
        without_top=without,
        years=by_year(trades, window, capital),
        halves=two,
        time_in_market=time_in_market(window),
        max_drawdown=max_drawdown(window["equity"], capital),
        closed_drawdown=max_drawdown(closed_trade_equity(trades, capital), capital),
        total_return=float(window["equity"].iloc[-1]) / capital - 1,
        buy_and_hold=bh,
    )
    analysis.checks = checks(analysis, criteria)
    return analysis


def checks(a: Analysis, c: Criteria) -> list[Check]:
    n = c.without_top_n
    pf = a.stats["profit_factor"]
    return [
        Check(
            "Profit factor (net)",
            f">= {c.min_profit_factor}",
            f"{pf:.3f}",
            pf >= c.min_profit_factor,
        ),
        Check(
            "Closed trades",
            f">= {c.min_trades}",
            str(a.stats["trades"]),
            a.stats["trades"] >= c.min_trades,
        ),
        Check(
            f"Net PnL without top {n} trades",
            "> 0",
            f"{a.without_top[n]:,.2f}",
            a.without_top[n] > 0,
        ),
        Check(
            "Net PnL first half",
            "> 0",
            f"{a.halves[0]['net_pnl']:,.2f}",
            a.halves[0]["net_pnl"] > 0,
        ),
        Check(
            "Net PnL second half",
            "> 0",
            f"{a.halves[1]['net_pnl']:,.2f}",
            a.halves[1]["net_pnl"] > 0,
        ),
        Check(
            "Return vs buy and hold",
            "comparison",
            f"{a.total_return:.2%} vs {a.buy_and_hold['return']:.2%}",
            None,
        ),
        Check(
            "Max drawdown vs buy and hold",
            "comparison",
            f"{a.max_drawdown[1]:.2%} vs {a.buy_and_hold['max_drawdown_pct']:.2%}",
            None,
        ),
        Check(
            "Time in market vs buy and hold",
            "comparison",
            f"{a.time_in_market:.2%} vs 100.00%",
            None,
        ),
    ]
