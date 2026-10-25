"""Parity with TradingView: same trades as the reference run of "EMA 9 / Rolling VWAP Cross v1".

Fixtures (from the TradingView Strategy Tester, not committed by the engine):
- tests/fixtures/tv_summary.csv: metric,value with trade_count, profit_factor, net_pnl,
  winning_trades, max_drawdown, chart_timezone, first_loaded_candle
- tests/fixtures/tv_trades.csv: number,side,entry_time,entry_price,exit_time,exit_price,
  exit_comment,net_pnl with times in chart_timezone

Pass criteria, fixed before the run: every reference trade has a trade with the same side and
entry time; entry and exit prices within 2 ticks; trade count within 2; profit factor within
0.02; net PnL within 2%. Failures are reported in full. Nothing is tuned to pass.
"""

import dataclasses
import warnings
from pathlib import Path

import pandas as pd
import pytest

from real_edge_backtest.data.paths import parquet_path
from real_edge_backtest.engine import load_config
from real_edge_backtest.engine.results import summarize, trades_frame
from real_edge_backtest.runner import run_backtest

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures"
SUMMARY = FIXTURES / "tv_summary.csv"
TRADES = FIXTURES / "tv_trades.csv"
CONFIG = ROOT / "configs" / "ema_vwap_parity.toml"
PRICE_TOLERANCE = 0.02  # 2 ticks of 0.01


def _config():
    config = load_config(CONFIG)
    return dataclasses.replace(config, data_dir=ROOT / config.data_dir)


missing = [p.name for p in (SUMMARY, TRADES) if not p.exists()]
pytestmark = [
    pytest.mark.skipif(
        bool(missing), reason=f"TradingView reference missing in tests/fixtures: {missing}"
    ),
    pytest.mark.skipif(
        not parquet_path(ROOT / "data", "BTCUSDT", "1h").exists(),
        reason="BTCUSDT 1h dataset missing, run 'real-edge-backtest data download' first",
    ),
]


@pytest.fixture(scope="module")
def reference():
    summary = pd.read_csv(SUMMARY, dtype=str).set_index("metric")["value"]
    tz = summary["chart_timezone"].strip()
    trades = pd.read_csv(TRADES)
    for column in ("entry_time", "exit_time"):
        trades[column] = pd.to_datetime(trades[column]).dt.tz_localize(tz).dt.tz_convert("UTC")
    trades["side"] = trades["side"].str.strip().str.lower()
    return summary, trades


@pytest.fixture(scope="module")
def ours():
    result = run_backtest(_config())
    return summarize(result), trades_frame(result)


def test_trade_count(reference, ours):
    expected = int(reference[0]["trade_count"])
    assert abs(ours[0].trades - expected) <= 2, f"ours {ours[0].trades}, TradingView {expected}"


def test_profit_factor(reference, ours):
    expected = float(reference[0]["profit_factor"])
    actual = ours[0].profit_factor
    assert abs(actual - expected) <= 0.02, f"ours {actual:.4f}, TradingView {expected}"


def test_net_pnl(reference, ours):
    expected = float(reference[0]["net_pnl"])
    actual = float(ours[0].net_pnl)
    assert abs(actual - expected) <= abs(expected) * 0.02, f"ours {actual:.2f}, TV {expected}"


def test_reference_trades_match(reference, ours):
    ref_trades = reference[1]
    mine = ours[1]
    problems = []
    for _, ref in ref_trades.iterrows():
        match = mine[(mine["side"] == ref["side"]) & (mine["entry_time"] == ref["entry_time"])]
        if match.empty:
            near = mine[(mine["entry_time"] - ref["entry_time"]).abs() <= pd.Timedelta(hours=2)]
            hint = near[["number", "side", "entry_time", "entry_price"]].to_dict("records")
            problems.append(
                f"#{ref['number']} {ref['side']} {ref['entry_time']}: no match, near {hint}"
            )
            continue
        trade = match.iloc[0]
        for field in ("entry_price", "exit_price"):
            diff = abs(trade[field] - ref[field])
            if not diff <= PRICE_TOLERANCE + 1e-9:
                problems.append(
                    f"#{ref['number']} {field}: ours {trade[field]}, TV {ref[field]} "
                    f"(diff {diff:.2f})"
                )
        # Not a pass criterion, reported for diagnosis only.
        if trade["exit_time"] != ref["exit_time"]:
            warnings.warn(
                f"#{ref['number']} exit_time: ours {trade['exit_time']}, TV {ref['exit_time']}",
                stacklevel=1,
            )
    assert not problems, "\n".join(problems)
