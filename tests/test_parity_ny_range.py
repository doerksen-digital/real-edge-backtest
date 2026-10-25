"""Parity with TradingView: same trades as the reference run of "NY 4H Range Re-entry
(BTCUSDT 5m)" with its default inputs.

Fixtures, written by hand from the TradingView Strategy Tester (see README), not committed:
- tests/fixtures/ny_range/tv_summary.csv: metric,value with trade_count, profit_factor,
  net_pnl, chart_timezone, first_loaded_candle, last_loaded_candle
- tests/fixtures/ny_range/tv_trades.csv: number,side,entry_time,entry_price,exit_time,
  exit_price,exit_comment,qty,net_pnl with times in chart_timezone; every closed trade

TradingView's 5m history starts inside a day, so that day's range can be incomplete there.
Trades entered on the NY day of first_loaded_candle are left out on both sides, unless that
candle opens at 00:00 NY. Only trades closed by last_loaded_candle are compared.

Pass criteria, fixed before the run: every compared reference trade has a trade with the same
side and entry time, the same exit time and exit comment, entry and exit price within 2 ticks
and net PnL within 0.02 USD or 0.1%, whichever is larger; trade count within 2; profit factor
within 0.02. The trade list must also add up to the Strategy Tester summary (a copy check).
Failures are reported in full. Nothing is tuned to pass. qty differences are reported as
warnings (they decide fee_reserve_pct, see README).
"""

import dataclasses
import warnings
from pathlib import Path

import pandas as pd
import pytest

from real_edge_backtest.data.paths import parquet_path
from real_edge_backtest.engine import load_config
from real_edge_backtest.engine.results import trades_frame
from real_edge_backtest.runner import run_backtest
from real_edge_backtest.strategies.ny_range import TZ

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "ny_range"
SUMMARY = FIXTURES / "tv_summary.csv"
TRADES = FIXTURES / "tv_trades.csv"
CONFIG = ROOT / "configs" / "ny_range_parity.toml"
PRICE_TOLERANCE = 0.02  # 2 ticks of 0.01


def _config():
    config = load_config(CONFIG)
    return dataclasses.replace(config, data_dir=ROOT / config.data_dir)


def profit_factor(net: pd.Series) -> float:
    loss = -net[net < 0].sum()
    return float(net[net > 0].sum() / loss) if loss else float("inf")


missing = [p.name for p in (SUMMARY, TRADES) if not p.exists()]
pytestmark = [
    pytest.mark.skipif(
        bool(missing), reason=f"TradingView reference missing in tests/fixtures/ny_range: {missing}"
    ),
    pytest.mark.skipif(
        not parquet_path(ROOT / "data", "BTCUSDT", "5m").exists(),
        reason="BTCUSDT 5m dataset missing, run 'real-edge-backtest data download' first",
    ),
]


@pytest.fixture(scope="module")
def reference():
    summary = pd.read_csv(SUMMARY, dtype=str).set_index("metric")["value"].str.strip()
    tz = summary["chart_timezone"]

    def utc(values):
        return pd.to_datetime(values).dt.tz_localize(tz).dt.tz_convert("UTC")

    trades = pd.read_csv(TRADES, dtype={"exit_comment": str})
    for column in ("entry_time", "exit_time"):
        trades[column] = utc(trades[column])
    trades["side"] = trades["side"].str.strip().str.lower()
    trades["exit_comment"] = trades["exit_comment"].fillna("").str.strip()
    first, last = utc(summary[["first_loaded_candle", "last_loaded_candle"]].reset_index(drop=True))
    return summary, trades, first, last


def compared(trades: pd.DataFrame, first: pd.Timestamp, last: pd.Timestamp) -> pd.DataFrame:
    """Closed trades entered from the first complete NY day on and closed by `last`."""
    local = first.tz_convert(TZ)
    day = local.normalize()
    begin = local if local == day else day + pd.DateOffset(days=1)
    keep = (
        (trades["entry_time"] >= begin.tz_convert("UTC"))
        & trades["exit_time"].notna()
        & (trades["exit_time"] <= last)
    )
    return trades[keep].reset_index(drop=True)


@pytest.fixture(scope="module")
def ours(reference):
    _, _, first, last = reference
    frame = trades_frame(run_backtest(_config()))
    return compared(frame, first, last)


@pytest.fixture(scope="module")
def theirs(reference):
    _, trades, first, last = reference
    return compared(trades, first, last)


def test_trade_list_adds_up_to_the_summary(reference):
    summary, trades, _, _ = reference
    assert len(trades) == int(summary["trade_count"]), "a trade is missing in tv_trades.csv"
    assert abs(trades["net_pnl"].sum() - float(summary["net_pnl"])) <= 0.05
    assert abs(profit_factor(trades["net_pnl"]) - float(summary["profit_factor"])) <= 0.005


def test_trade_count(ours, theirs):
    assert abs(len(ours) - len(theirs)) <= 2, f"ours {len(ours)}, TradingView {len(theirs)}"


def test_profit_factor(ours, theirs):
    actual, expected = profit_factor(ours["net_pnl"]), profit_factor(theirs["net_pnl"])
    assert abs(actual - expected) <= 0.02, f"ours {actual:.4f}, TradingView {expected:.4f}"


def test_reference_trades_match(ours, theirs):
    problems = []
    for _, ref in theirs.iterrows():
        match = ours[(ours["side"] == ref["side"]) & (ours["entry_time"] == ref["entry_time"])]
        if match.empty:
            near = ours[(ours["entry_time"] - ref["entry_time"]).abs() <= pd.Timedelta(hours=2)]
            hint = near[["number", "side", "entry_time", "entry_price"]].to_dict("records")
            problems.append(
                f"#{ref['number']} {ref['side']} {ref['entry_time']}: no match, near {hint}"
            )
            continue
        trade = match.iloc[0]
        tag = f"#{ref['number']} {ref['entry_time']}"
        for field in ("entry_price", "exit_price"):
            diff = abs(trade[field] - ref[field])
            if not diff <= PRICE_TOLERANCE + 1e-9:
                problems.append(f"{tag} {field}: ours {trade[field]}, TV {ref[field]}")
        for field in ("exit_time", "exit_comment"):
            if trade[field] != ref[field]:
                problems.append(f"{tag} {field}: ours {trade[field]}, TV {ref[field]}")
        tolerance = max(0.02, abs(ref["net_pnl"]) * 0.001)
        if not abs(trade["net_pnl"] - ref["net_pnl"]) <= tolerance + 1e-9:
            problems.append(f"{tag} net_pnl: ours {trade['net_pnl']:.2f}, TV {ref['net_pnl']}")
        # Not a pass criterion: the ratio tells whether TradingView keeps a fee reserve.
        if "qty" in ref and abs(trade["qty"] - ref["qty"]) > 1e-9:
            warnings.warn(
                f"{tag} qty: ours {trade['qty']}, TV {ref['qty']} "
                f"(ratio {ref['qty'] / trade['qty']:.6f})",
                stacklevel=1,
            )
    assert not problems, "\n".join(problems)
