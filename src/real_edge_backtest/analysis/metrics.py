"""Trade and equity metrics from a run folder (trades.csv, equity.csv, run.json).

Reads result files only, so any run folder can be analyzed without the engine. Every equity
based number uses the curve cut to the run window (window_equity); the full-dataset curve in
equity.csv is never used directly.

Definitions:
- closed trades only; profit factor = sum of winning net PnL / -sum of losing net PnL
- a trade belongs to the calendar year (UTC) and half of the window in which it exits; a bar
  belongs to the year of its open time
- time in market = share of window bars entered with an open position
- "without the best trades", return method (the pass criterion): each closed trade's net PnL
  as a fraction of equity at its entry (starting capital plus the net PnL of all earlier
  trades), the best N winners by that return removed, the rest compounded in entry order from
  the starting capital. The USD method (subtracting the best trades' USD PnL) is reported
  too, but under percent_equity sizing later trades are larger in USD only because equity
  grew, so it is distorted by compounding.
- costs: fees are the commission column. Fill prices already include slippage, so gross_pnl
  is after slippage and before fees; slippage per closed trade = 2 fills x slippage_ticks x
  tick x qty x point value. "Gross move" is the price move between the unslipped entry and
  exit prices, signed by side, in % of the unslipped entry price; fee, slippage and
  round-trip cost % are over the entry notional
- percent return of a trade = trade_returns (net return on equity at entry); the best and
  worst 1% of trades are ranked by it
- rolling 12 months: at each month start, PF of the trades that exited in the 12 months
  before it and the window-equity return over the same 12 months
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
    min_trades: int = 100
    without_top_n: int = 5  # still positive without the N best trades
    without_top_pct: float = 1.0  # and without the best pct % of trades (count rounded up)
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


def with_returns(trades: pd.DataFrame, initial: float) -> pd.DataFrame:
    """Closed trades in entry order with a return column: net PnL over equity at entry.
    Positions never overlap, so equity at entry = starting capital + net PnL of all earlier
    trades."""
    t = closed(trades).sort_values("entry_time").reset_index(drop=True)
    equity_at_entry = initial + t["net_pnl"].cumsum().shift(1, fill_value=0.0)
    return t.assign(**{"return": t["net_pnl"] / equity_at_entry})


def trade_returns(trades: pd.DataFrame, initial: float) -> pd.Series:
    """Net return of each closed trade on equity at its entry, in entry order."""
    return with_returns(trades, initial)["return"]


def tail_trades(
    trades: pd.DataFrame, initial: float, pct: float
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Best and worst pct percent of closed trades (count rounded up) by percent return."""
    t = with_returns(trades, initial)
    n = top_pct_count(len(t), pct)
    return t.nlargest(n, "return"), t.nsmallest(n, "return")


def compounded_without_top(returns: pd.Series, initial: float, n: int) -> float:
    """Net PnL from compounding the returns in order after removing the n best winning ones."""
    top = returns[returns > 0].nlargest(n).index
    kept = returns.drop(index=top)
    return float(initial * (1 + kept).prod() - initial)


def top_pct_count(trade_count: int, pct: float) -> int:
    """Number of trades in the top `pct` percent of `trade_count`, rounded up."""
    return math.ceil(Fraction(trade_count) * Fraction(str(pct)) / 100)


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


def by_year_side(trades: pd.DataFrame) -> pd.DataFrame:
    """Trade stats per exit year and side."""
    t = closed(trades)
    rows = []
    for year in sorted(t["exit_time"].dt.year.unique()):
        for side in ("long", "short"):
            part = t[(t["exit_time"].dt.year == year) & (t["side"] == side)]
            rows.append({"year": int(year), "side": side, **trade_stats(part)})
    return pd.DataFrame(rows)


def slippage_cost(trades: pd.DataFrame, broker: dict[str, Any]) -> pd.Series:
    """Slippage paid per trade in money: two fills of slippage_ticks ticks each."""
    per_unit = broker["slippage_ticks"] * float(broker["tick_size"]) * float(broker["point_value"])
    return 2 * per_unit * trades["qty"]


def _profit_factor(pnl: pd.Series) -> float:
    gross_loss = -pnl[pnl < 0].sum()
    return float(pnl[pnl > 0].sum() / gross_loss) if gross_loss else math.inf


def cost_stats(trades: pd.DataFrame, broker: dict[str, Any]) -> dict[str, float]:
    """Profit factor before fees and before fees and slippage, and the costs paid."""
    t = closed(trades)
    slip = slippage_cost(t, broker)
    gross = t["gross_pnl"]
    return {
        "profit_factor_before_fees": _profit_factor(gross),
        "profit_factor_before_costs": _profit_factor(gross + slip),
        "fees": float(t["commission"].sum()),
        "slippage": float(slip.sum()),
        "gross_pnl": float(gross.sum()),
        "gross_pnl_before_costs": float((gross + slip).sum()),
    }


def trade_moves(trades: pd.DataFrame, broker: dict[str, Any]) -> pd.DataFrame:
    """Closed trades with the gross move (unslipped prices, signed by side, fraction of the
    entry price), the entry notional, and fee, slippage and round-trip cost as fractions of
    the entry notional."""
    t = closed(trades)
    slip = broker["slippage_ticks"] * float(broker["tick_size"])
    side = t["side"].map({"long": 1, "short": -1})
    entry = t["entry_price"] - side * slip
    exit_ = t["exit_price"] + side * slip
    notional = t["qty"] * t["entry_price"] * float(broker["point_value"])
    slippage = slippage_cost(t, broker)
    return t.assign(
        move_pct=side * (exit_ - entry) / entry,
        notional=notional,
        fee_pct=t["commission"] / notional,
        slippage_pct=slippage / notional,
        cost_pct=(t["commission"] + slippage) / notional,
    )


def _mean(values: pd.Series) -> float:
    return float(values.mean()) if len(values) else math.nan


def year_costs(trades: pd.DataFrame, window: pd.DataFrame, broker: dict[str, Any]) -> pd.DataFrame:
    """Per calendar year: average ATR as a fraction of the close over the window bars (if
    equity.csv has an atr column), and per trade (by exit year) the average gross move,
    round-trip fee and slippage."""
    moves = trade_moves(trades, broker)
    exit_year = moves["exit_time"].dt.year
    bar_year = window["open_time"].dt.year
    atr_pct = window["atr"] / window["close"] if "atr" in window else None
    rows = []
    for year in sorted(set(bar_year.unique()) | set(exit_year.unique())):
        m = moves[exit_year == year]
        rows.append(
            {
                "year": int(year),
                "atr_pct": math.nan if atr_pct is None else _mean(atr_pct[bar_year == year]),
                "trades": int(len(m)),
                "abs_move_pct": _mean(m["move_pct"].abs()),
                "move_pct": _mean(m["move_pct"]),
                "fee": _mean(m["commission"]),
                "fee_pct": _mean(m["fee_pct"]),
                "slippage_pct": _mean(m["slippage_pct"]),
                "fees": float(m["commission"].sum()),
                "slippage": float(slippage_cost(m, broker).sum()),
            }
        )
    return pd.DataFrame(rows)


def rolling_12m(trades: pd.DataFrame, window: pd.DataFrame) -> pd.DataFrame:
    """At each month start with 12 full months of window behind it: PF of the trades that
    exited in those 12 months and the window-equity return over them."""
    t = closed(trades)
    equity = window.set_index("time_close")["equity"]
    first, last = equity.index[0], equity.index[-1]
    rows = []
    for point in pd.date_range(first + pd.DateOffset(months=12), last, freq="MS"):
        begin = point - pd.DateOffset(months=12)
        part = t[(t["exit_time"] >= begin) & (t["exit_time"] < point)]
        now = float(equity[equity.index <= point].iloc[-1])
        then = float(equity[equity.index <= begin].iloc[-1])
        rows.append(
            {
                "time": point,
                "trades": int(len(part)),
                "profit_factor": _profit_factor(part["net_pnl"]) if len(part) else math.nan,
                "return": now / then - 1,
            }
        )
    return pd.DataFrame(rows, columns=["time", "trades", "profit_factor", "return"])


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
    without_top_pct: tuple[float, int, float]  # (pct, trades removed, net PnL without them)
    # Return method, used by the pass criterion; the two fields above are the USD method.
    without_top_return: dict[int, float]
    without_top_pct_return: tuple[float, int, float]
    years: pd.DataFrame
    halves: list[dict]
    time_in_market: float
    max_drawdown: tuple[float, float]
    closed_drawdown: tuple[float, float]
    total_return: float
    buy_and_hold: dict[str, Any]
    costs: dict[str, float] = field(default_factory=dict)
    years_side: pd.DataFrame | None = None
    year_costs: pd.DataFrame | None = None
    best: pd.DataFrame | None = None  # best without_top_pct % of trades by percent return
    worst: pd.DataFrame | None = None
    rolling: pd.DataFrame | None = None
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
    removed = top_pct_count(stats["trades"], criteria.without_top_pct)
    pct = (criteria.without_top_pct, removed, pnl_without_top(trades, removed))
    returns = trade_returns(trades, capital)
    without_return = {n: compounded_without_top(returns, capital, n) for n in without}
    pct_return = (
        criteria.without_top_pct,
        removed,
        compounded_without_top(returns, capital, removed),
    )
    two = halves(trades, run.start, run.end)
    broker = run.meta["broker"]
    bh = buy_and_hold(window, broker)
    best, worst = tail_trades(trades, capital, criteria.without_top_pct)
    analysis = Analysis(
        window=window,
        stats=stats,
        without_top=without,
        without_top_pct=pct,
        without_top_return=without_return,
        without_top_pct_return=pct_return,
        years=by_year(trades, window, capital),
        halves=two,
        time_in_market=time_in_market(window),
        max_drawdown=max_drawdown(window["equity"], capital),
        closed_drawdown=max_drawdown(closed_trade_equity(trades, capital), capital),
        total_return=float(window["equity"].iloc[-1]) / capital - 1,
        buy_and_hold=bh,
        costs=cost_stats(trades, broker),
        years_side=by_year_side(trades),
        year_costs=year_costs(trades, window, broker),
        best=best,
        worst=worst,
        rolling=rolling_12m(trades, window),
    )
    analysis.checks = checks(analysis, criteria)
    return analysis


def checks(a: Analysis, c: Criteria) -> list[Check]:
    n = c.without_top_n
    pct, removed, without_pct = a.without_top_pct_return
    without_n = a.without_top_return[n]
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
            "Net PnL without the best trades (return method)",
            f"> 0 without top {n} and without top {pct:g}% ({removed} trades)",
            f"top {n}: {without_n:,.2f}; top {pct:g}%: {without_pct:,.2f}",
            without_n > 0 and without_pct > 0,
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
