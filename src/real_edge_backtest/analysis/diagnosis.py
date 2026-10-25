"""Descriptive diagnosis of one run from its result files (trades.csv, trades_enriched.csv,
run.json). Prints markdown tables; it does not change or run anything.

    python -m real_edge_backtest.analysis.diagnosis runs/<run> [--out file.md]

All aggregates use percent returns on equity at entry (analysis.metrics.with_returns), so
every trade weighs the same whatever the equity was; USD sums would let the later, larger
trades of a compounding run dominate. Per trade:
- net return = net PnL / equity at entry; gross return = gross PnL (after slippage, before
  fees) / equity at entry; fee return = commission / equity at entry
- PF net and PF gross = sum of positive / -sum of negative returns
- fee share of gross profit = sum of fee returns / sum of positive gross returns

Groups: the best and the worst 1% of closed trades by net return (count rounded up) and all
other trades. Cells with fewer than MIN_CELL trades are marked "few".
"""

import argparse
import math
import sys
from pathlib import Path

import pandas as pd

from real_edge_backtest.analysis.metrics import load_run, top_pct_count, trade_moves, with_returns

MIN_CELL = 30
QUANTILES = (0.1, 0.25, 0.5, 0.75, 0.9)
GROUPS = ("top 1%", "bottom 1%", "rest")

ENTRY_FEATURES = {
    "atr_pct": "ATR % of price",
    "dist_daily_ema_atr": "close - daily EMA, in ATR",
    "daily_ema_slope_pct": "daily EMA slope, % per day",
    "sep_atr_side": "EMA - VWAP in ATR, in trade direction",
    "crosses_24": "crosses in previous 24 bars",
    "crosses_48": "crosses in previous 48 bars",
    "vol_ratio_24": "volume / 24-bar average",
    "vol_ratio_7d": "volume / 7-day average",
    "hour_utc": "entry hour UTC",
    "weekday_utc": "entry weekday UTC (0 = Monday)",
}
TRADE_MEASURES = {
    "mfe_pct": "MFE %",
    "mae_pct": "MAE %",
    "mfe_atr": "MFE in ATR",
    "mae_atr": "MAE in ATR",
    "realized_pct": "realized gross move %",
    "giveback_pct": "giveback % (MFE - realized)",
    "bars_held": "bars held",
    "mfe_bar": "bar of MFE",
}
COUNTS = {"crosses_24", "crosses_48", "hour_utc", "weekday_utc", "bars_held", "mfe_bar"}
PERCENT = {"atr_pct", "daily_ema_slope_pct", "mfe_pct", "mae_pct", "realized_pct", "giveback_pct"}


def load(folder: Path) -> pd.DataFrame:
    """Closed trades with returns, costs, entry features, excursions and the group."""
    run = load_run(folder)
    enriched = pd.read_csv(folder / "trades_enriched.csv")
    t = with_returns(run.trades, run.initial_capital)
    equity_at_entry = t["net_pnl"] / t["return"]
    moves = trade_moves(run.trades, run.meta["broker"]).set_index("number")
    t = t.assign(
        gross_return=t["gross_pnl"] / equity_at_entry,
        fee_return=t["commission"] / equity_at_entry,
        move_pct=t["number"].map(moves["move_pct"]),
        cost_pct=t["number"].map(moves["cost_pct"]),
        year=t["exit_time"].dt.year,
    )
    features = [c for c in enriched.columns if c in ENTRY_FEATURES or c in TRADE_MEASURES]
    t = t.merge(enriched[["number", "exit_by_stop", *features]], on="number", how="left")
    n = top_pct_count(len(t), 1)
    group = pd.Series("rest", index=t.index)
    group[t.nsmallest(n, "return").index] = "bottom 1%"
    group[t.nlargest(n, "return").index] = "top 1%"
    return t.assign(group=group)


# Formatting ----------------------------------------------------------------------------------


def _fmt(value: float, name: str = "") -> str:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return ""
    if isinstance(value, float) and math.isinf(value):
        return "inf"
    if name in PERCENT:
        return f"{value * 100:.2f}%"
    if name in COUNTS:
        return f"{value:.1f}"
    return f"{value:.3f}"


def _md(headers: list[str], rows: list[list[str]]) -> str:
    lines = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    lines += ["| " + " | ".join(str(c) for c in row) + " |" for row in rows]
    return "\n".join(lines)


def _pf(values: pd.Series) -> float:
    if not len(values):
        return math.nan
    loss = -values[values < 0].sum()
    return float(values[values > 0].sum() / loss) if loss else math.inf


def _few(n: int) -> str:
    return f"{n} (few)" if n < MIN_CELL else str(n)


# Tables --------------------------------------------------------------------------------------


def stats(t: pd.DataFrame) -> dict[str, float]:
    gross_profit = t["gross_return"][t["gross_return"] > 0].sum()
    return {
        "trades": len(t),
        "pf_net": _pf(t["return"]),
        "pf_gross": _pf(t["gross_return"]),
        "net": float(t["return"].sum()),
        "fee_share": float(t["fee_return"].sum() / gross_profit) if gross_profit else math.nan,
        "bars": float(t["bars_held"].mean()) if len(t) else math.nan,
        "win_rate": float((t["return"] > 0).mean()) if len(t) else math.nan,
    }


STATS_HEADERS = [
    "Trades",
    "PF net",
    "PF gross",
    "Net (sum of % returns)",
    "Fee share of gross profit",
    "Avg bars held",
    "Win rate",
]


def stats_cells(s: dict[str, float]) -> list[str]:
    return [
        _few(s["trades"]),
        _fmt(s["pf_net"]),
        _fmt(s["pf_gross"]),
        f"{s['net'] * 100:.1f}%",
        "" if math.isnan(s["fee_share"]) else f"{s['fee_share'] * 100:.0f}%",
        "" if math.isnan(s["bars"]) else f"{s['bars']:.1f}",
        "" if math.isnan(s["win_rate"]) else f"{s['win_rate'] * 100:.0f}%",
    ]


def overview(t: pd.DataFrame) -> str:
    rows = [
        [label, *stats_cells(stats(part))]
        for label, part in [
            ("all", t),
            ("long", t[t["side"] == "long"]),
            ("short", t[t["side"] == "short"]),
            *[(g, t[t["group"] == g]) for g in GROUPS],
        ]
    ]
    return _md(["Group", *STATS_HEADERS], rows)


def distribution(t: pd.DataFrame, column: str) -> str:
    rows = []
    for side in ("all", "long", "short"):
        part = t if side == "all" else t[t["side"] == side]
        for g in GROUPS:
            values = part.loc[part["group"] == g, column].dropna()
            q = values.quantile(QUANTILES) if len(values) else pd.Series(dtype=float)
            rows.append(
                [
                    f"{g}, {side}",
                    _few(len(values)),
                    *[_fmt(q.get(x, math.nan), column) for x in QUANTILES],
                ]
            )
    return _md(["Group", "n", "p10", "p25", "median", "p75", "p90"], rows)


def by_year(t: pd.DataFrame, column: str) -> str:
    rows = []
    for year, part in t.groupby("year"):
        cells = [str(year)]
        for g in GROUPS:
            values = part.loc[part["group"] == g, column].dropna()
            median = _fmt(values.median(), column) if len(values) else ""
            cells.append(f"{median} ({_few(len(values))})" if g != "rest" else median)
        cells.append(_few(int((part["group"] == "rest").sum())))
        rows.append(cells)
    return _md(["Year", "median top 1% (n)", "median bottom 1% (n)", "median rest", "n rest"], rows)


def bins(t: pd.DataFrame, column: str) -> pd.Series:
    """Quintiles, tie-safe; discrete features use values (hours in blocks of 4, crosses 0-4+)."""
    values = t[column]
    if column == "hour_utc":
        return (values // 4 * 4).map(lambda h: f"{int(h):02d}-{int(h) + 3:02d}")
    if column == "weekday_utc":
        return values.map(lambda d: ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"][int(d)])
    if column.startswith("crosses_"):
        return values.map(lambda c: "na" if pd.isna(c) else ("4+" if c >= 4 else str(int(c))))
    codes = pd.qcut(values.rank(method="first"), 5, labels=False)
    labels = {}
    for code in range(5):
        part = values[codes == code]
        labels[code] = f"Q{code + 1} {_fmt(part.min(), column)} to {_fmt(part.max(), column)}"
    return codes.map(labels).fillna("na")


def stability(t: pd.DataFrame, mid: pd.Timestamp) -> str:
    """PF net per bin of each entry feature in the first and the second half of the window
    (by exit), all trades, to show which bin patterns hold in both halves."""
    first = t["exit_time"] < mid
    rows = []
    for column, label in ENTRY_FEATURES.items():
        keys = bins(t, column)
        for key in sorted(keys.unique(), key=_bin_order):
            a, b = t[(keys == key) & first], t[(keys == key) & ~first]
            rows.append(
                [
                    label,
                    key,
                    _few(len(a)),
                    _fmt(_pf(a["return"])),
                    _few(len(b)),
                    _fmt(_pf(b["return"])),
                ]
            )
    return _md(
        ["Feature", "Bin", "n 1st half", "PF net 1st half", "n 2nd half", "PF net 2nd half"], rows
    )


def quintiles(t: pd.DataFrame, column: str) -> str:
    """Bins over all trades, then over the long and the short trades separately (the trend
    filter makes many features one-sided, so bins over all trades leave one side empty)."""
    rows = []
    for side in ("all", "long", "short"):
        part = t if side == "all" else t[t["side"] == side]
        keys = bins(part, column)
        for key in sorted(keys.unique(), key=_bin_order):
            rows.append([side, key, *stats_cells(stats(part[keys == key]))])
    return _md(["Side", "Bin", *STATS_HEADERS], rows)


def _bin_order(key: str) -> tuple:
    days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    if key in days:
        return (0, days.index(key))
    if key.startswith("Q"):
        return (0, int(key[1]))
    if key == "na":
        return (2, 0)
    head = key.rstrip("+").split("-")[0]
    return (1, int(head)) if head.isdigit() else (3, key)


# Specific questions --------------------------------------------------------------------------


def giveback(t: pd.DataFrame) -> str:
    rows = []
    for label, part in [
        ("winners (net > 0)", t[t["return"] > 0]),
        ("top 1%", t[t["group"] == "top 1%"]),
        ("losers (net <= 0)", t[t["return"] <= 0]),
    ]:
        mfe, real = part["mfe_pct"], part["realized_pct"]
        rows.append(
            [
                label,
                _few(len(part)),
                _fmt(mfe.median(), "mfe_pct"),
                _fmt(real.median(), "realized_pct"),
                _fmt(part["giveback_pct"].median(), "giveback_pct"),
                f"{(part['giveback_pct'] / mfe.where(mfe > 0)).median() * 100:.0f}%",
                f"{(real < 0.5 * mfe).mean() * 100:.0f}%",
                f"{(part['mfe_atr'] >= 1).mean() * 100:.0f}%",
            ]
        )
    return _md(
        [
            "Trades",
            "n",
            "median MFE",
            "median realized",
            "median giveback",
            "median giveback / MFE",
            "realized < half of MFE",
            "MFE >= 1 ATR",
        ],
        rows,
    )


def giveback_by_mfe(t: pd.DataFrame) -> str:
    """How trades that reached a given MFE (in ATR at entry) ended."""
    edges = [(0, 1), (1, 2), (2, 3), (3, 5), (5, math.inf)]
    rows = []
    for lo, hi in edges:
        part = t[(t["mfe_atr"] >= lo) & (t["mfe_atr"] < hi)]
        if not len(part):
            continue
        realized_atr = part["realized_pct"] / part["atr_pct"]
        rows.append(
            [
                f"{lo} to {hi} ATR" if hi != math.inf else f">= {lo} ATR",
                str(len(part)),
                f"{len(part) / len(t) * 100:.0f}%",
                _fmt(part["mfe_atr"].median()),
                _fmt(realized_atr.median()),
                f"{(part['return'] <= 0).mean() * 100:.0f}%",
                f"{part['return'].sum() * 100:.1f}%",
                f"{part['exit_by_stop'].astype(bool).mean() * 100:.0f}%",
            ]
        )
    return _md(
        [
            "MFE reached",
            "n",
            "share of trades",
            "median MFE (ATR)",
            "median realized (ATR)",
            "ended as loser",
            "sum of % returns",
            "exited by stop",
        ],
        rows,
    )


def loser_mass(t: pd.DataFrame) -> str:
    losers = t[t["return"] < 0].copy()
    total = losers["return"].sum()
    size_atr = (-losers["realized_pct"] / losers["atr_pct"]).clip(lower=0)
    buckets = {
        "stopped out (ATR stop)": losers["exit_by_stop"].astype(bool),
        "cross exit, gross move against < 0.5 ATR": ~losers["exit_by_stop"].astype(bool)
        & (size_atr < 0.5),
        "cross exit, 0.5 to 1 ATR": ~losers["exit_by_stop"].astype(bool)
        & (size_atr >= 0.5)
        & (size_atr < 1),
        "cross exit, >= 1 ATR": ~losers["exit_by_stop"].astype(bool) & (size_atr >= 1),
    }
    rows = []
    for label, mask in buckets.items():
        part = losers[mask]
        rows.append(
            [
                label,
                str(len(part)),
                f"{len(part) / len(losers) * 100:.0f}%",
                f"{part['return'].sum() * 100:.1f}%",
                f"{part['return'].sum() / total * 100:.0f}%",
                f"{part['fee_return'].sum() / -part['return'].sum() * 100:.0f}%"
                if len(part)
                else "",
            ]
        )
    table = _md(
        [
            "Losers",
            "n",
            "share of losers",
            "sum of % returns",
            "share of total loss",
            "fees as share of their loss",
        ],
        rows,
    )
    ordered = losers["return"].sort_values(ascending=False)  # smallest losses first
    cum = ordered.cumsum() / total
    deciles = []
    for k in range(1, 11):
        n = math.ceil(len(ordered) * k / 10)
        deciles.append(
            [
                f"smallest {k * 10}%",
                str(n),
                _fmt(-ordered.iloc[n - 1], "realized_pct"),
                f"{cum.iloc[n - 1] * 100:.0f}%",
            ]
        )
    curve = _md(
        ["Losers, smallest first", "n", "largest loss in this set", "share of total loss"], deciles
    )
    return table + "\n\nCumulative loss, losers sorted from the smallest loss:\n\n" + curve


def chop(t: pd.DataFrame) -> str:
    rows = []
    for label, part in [
        ("0-1 crosses in 48 bars", t[t["crosses_48"] <= 1]),
        ("2-3", t[(t["crosses_48"] >= 2) & (t["crosses_48"] <= 3)]),
        ("4-5", t[(t["crosses_48"] >= 4) & (t["crosses_48"] <= 5)]),
        ("6+", t[t["crosses_48"] >= 6]),
    ]:
        s = stats(part)
        rows.append(
            [
                label,
                *stats_cells(s),
                _fmt(part["atr_pct"].median(), "atr_pct"),
                _fmt(part["sep_atr_side"].median()),
                _fmt(part["mfe_atr"].median()),
                _fmt(part["move_pct"].abs().median(), "realized_pct"),
            ]
        )
    return _md(
        [
            "Recent crosses",
            *STATS_HEADERS,
            "median ATR %",
            "median separation (ATR)",
            "median MFE (ATR)",
            "median abs gross move",
        ],
        rows,
    )


def chop_by_year(t: pd.DataFrame) -> str:
    rows = []
    for year, part in t.groupby("year"):
        rows.append(
            [
                str(year),
                str(len(part)),
                f"{(part['crosses_48'] >= 4).mean() * 100:.0f}%",
                _fmt(part["crosses_48"].mean()),
            ]
        )
    return _md(["Year", "trades", "share with >= 4 crosses in 48 bars", "mean crosses_48"], rows)


def fees_vs_moves(t: pd.DataFrame) -> str:
    rows = []
    for year, part in t.groupby("year"):
        abs_move = part["move_pct"].abs()
        rows.append(
            [
                str(year),
                str(len(part)),
                _fmt(part["atr_pct"].mean(), "atr_pct"),
                _fmt(abs_move.mean(), "realized_pct"),
                _fmt(abs_move.median(), "realized_pct"),
                _fmt(part["cost_pct"].mean(), "realized_pct"),
                f"{part['cost_pct'].mean() / abs_move.mean() * 100:.1f}%",
                f"{(abs_move < part['cost_pct']).mean() * 100:.0f}%",
                _fmt(_pf(part["gross_return"])),
                _fmt(_pf(part["return"])),
            ]
        )
    return _md(
        [
            "Year",
            "trades",
            "mean ATR % at entry",
            "mean abs gross move",
            "median abs gross move",
            "mean round-trip cost",
            "cost / mean abs move",
            "moves smaller than cost",
            "PF gross",
            "PF net",
        ],
        rows,
    )


def render(folder: Path) -> str:
    t = load(folder)
    run = load_run(folder)
    mid = run.start + (run.end - run.start) / 2
    n = top_pct_count(len(t), 1)
    parts = [
        f"Run folder: `{folder.as_posix()}`. {len(t)} closed trades; top and bottom 1% = {n} "
        "trades each by net return on equity at entry. Cells with fewer than "
        f"{MIN_CELL} trades are marked (few).",
        "### Overview\n\n" + overview(t),
        "### Giveback\n\n"
        + giveback(t)
        + "\n\nBy the MFE a trade reached:\n\n"
        + giveback_by_mfe(t),
        "### Where the losses come from\n\n" + loser_mass(t),
        "### Recent crosses (chop)\n\n" + chop(t) + "\n\n" + chop_by_year(t),
        "### Fees and move size per year (by exit)\n\n" + fees_vs_moves(t),
        "### Entry features by quintile\n\nQuintiles over all trades, then within the long and "
        "within the short trades; discrete features by value. PF and net from percent returns.",
    ]
    for column, label in ENTRY_FEATURES.items():
        parts.append(f"#### {label} (`{column}`)\n\n" + quintiles(t, column))
    parts.append(
        f"### Bin patterns in both halves (split at {mid:%Y-%m-%d %H:%M} UTC, by exit)\n\n"
        + stability(t, mid)
    )
    parts.append("### Distributions per group")
    for column, label in {**ENTRY_FEATURES, **TRADE_MEASURES}.items():
        parts.append(
            f"#### {label} (`{column}`)\n\n"
            + distribution(t, column)
            + "\n\nMedian per exit year:\n\n"
            + by_year(t, column)
        )
    return "\n\n".join(parts) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m real_edge_backtest.analysis.diagnosis")
    parser.add_argument("run", type=Path, help="run folder with trades_enriched.csv")
    parser.add_argument("--out", type=Path, help="markdown file to write (default: stdout)")
    args = parser.parse_args(argv)
    text = render(args.run)
    if args.out:
        args.out.write_bytes(text.encode("utf-8"))
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
