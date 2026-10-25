"""Compare the trades of two run folders (A and B). Reads result files only.

A trade is identified by its side and entry time. Between A and B a trade has:
- disappeared: in A, no B trade with the same side and entry time
- appeared: in B only
- changed: in both, but the exit (time or price) differs
- same exit: in both with the same exit; its size and PnL may still differ, because under
  percent_equity sizing every earlier change moves equity

For A's best trades by percent return (the top without_top_pct %), the comparison says what
B did instead: the same trade, the trade with another exit, or, if B has no such trade,
which B trade was open at that entry time, or that B was flat.
"""

from dataclasses import dataclass

import pandas as pd

from real_edge_backtest.analysis.metrics import Run, top_pct_count, with_returns

KEY = ["side", "entry_time"]


@dataclass
class TradeDiff:
    disappeared: pd.DataFrame  # A rows
    appeared: pd.DataFrame  # B rows
    changed: pd.DataFrame  # merged rows, columns suffixed _a and _b
    same_exit: int


def diff_trades(a: pd.DataFrame, b: pd.DataFrame) -> TradeDiff:
    merged = a.merge(b, on=KEY, how="outer", suffixes=("_a", "_b"), indicator=True)
    only_a = merged[merged["_merge"] == "left_only"]
    only_b = merged[merged["_merge"] == "right_only"]
    both = merged[merged["_merge"] == "both"]
    exit_time_differs = ~(
        (both["exit_time_a"] == both["exit_time_b"])
        | (both["exit_time_a"].isna() & both["exit_time_b"].isna())
    )
    exit_price_differs = ~(
        (both["exit_price_a"] == both["exit_price_b"])
        | (both["exit_price_a"].isna() & both["exit_price_b"].isna())
    )
    changed = both[exit_time_differs | exit_price_differs]
    return TradeDiff(
        disappeared=a.merge(only_a[KEY], on=KEY),
        appeared=b.merge(only_b[KEY], on=KEY),
        changed=changed.drop(columns="_merge").reset_index(drop=True),
        same_exit=int(len(both) - len(changed)),
    )


def open_at(trades: pd.DataFrame, time: pd.Timestamp) -> pd.DataFrame:
    """Trades holding a position after the close of the bar that opens at `time`: entered at
    or before that bar and exited after it (or still open)."""
    entered = trades["entry_time"] <= time
    still_open = trades["exit_time"].isna() | (trades["exit_time"] > time)
    return trades[entered & still_open]


def top_fate(run_a: Run, run_b: Run, pct: float) -> pd.DataFrame:
    """What B did with each of A's best pct % of trades by percent return."""
    a = with_returns(run_a.trades, run_a.initial_capital)
    b = with_returns(run_b.trades, run_b.initial_capital)
    best = a.nlargest(top_pct_count(len(a), pct), "return")
    rows = []
    for _, t in best.iterrows():
        match = b[(b["side"] == t["side"]) & (b["entry_time"] == t["entry_time"])]
        row = {
            "number_a": int(t["number"]),
            "side": t["side"],
            "entry_time": t["entry_time"],
            "exit_time_a": t["exit_time"],
            "return_a": float(t["return"]),
            "net_pnl_a": float(t["net_pnl"]),
        }
        if len(match):
            m = match.iloc[0]
            same = m["exit_time"] == t["exit_time"] and m["exit_price"] == t["exit_price"]
            row.update(
                outcome="in B, same exit" if same else "in B, exit changed",
                number_b=int(m["number"]),
                exit_time_b=m["exit_time"],
                return_b=float(m["return"]),
                net_pnl_b=float(m["net_pnl"]),
                note="",
            )
        else:
            busy = open_at(run_b.trades, t["entry_time"])
            note = (
                "B was flat at that entry"
                if busy.empty
                else "B was in trade #{} ({}, entered {:%Y-%m-%d %H:%M})".format(
                    int(busy.iloc[0]["number"]), busy.iloc[0]["side"], busy.iloc[0]["entry_time"]
                )
            )
            row.update(outcome="missing in B", note=note)
        rows.append(row)
    return pd.DataFrame(rows)
