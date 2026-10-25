"""HTML report from a small run folder: self-contained and complete."""

import re

import pytest

from conftest import random_walk
from real_edge_backtest.cli import main
from real_edge_backtest.engine import Backtest, BrokerConfig
from real_edge_backtest.engine.results import write_run
from real_edge_backtest.report.html import write_report
from real_edge_backtest.strategies.ema_vwap import EmaVwap

PARAMS = {"start": "2025-01-03T00:00:00Z", "end": "2025-02-20T00:00:00Z"}
META = {
    "name": "case",
    "strategy": "ema_vwap",
    "symbol": "TEST",
    "interval": "1h",
    "window": {"start": PARAMS["start"], "end": PARAMS["end"]},
    "broker": {
        "initial_capital": "10000",
        "commission_pct": "0.05",
        "slippage_ticks": 2,
        "tick_size": "0.01",
        "lot_size": "0.00001",
        "point_value": "1",
        "fill_model": "pessimistic",
    },
    "criteria": {},
    "provenance": {"commit": "abc123", "dirty": False, "config_sha256": "c0", "data_sha256": "d0"},
    "warnings": ["Start is only 2 days after the first candle"],
}


@pytest.fixture
def run_folder(tmp_path):
    result = Backtest(random_walk(1500, 7), EmaVwap, BrokerConfig(), PARAMS).run()
    return write_run(result, tmp_path, "case", "", META)


def test_report_is_self_contained_and_complete(run_folder):
    text = write_report(run_folder).read_text(encoding="utf-8")
    for section in (
        "Pass criteria",
        "Trade metrics",
        "Buy and hold",
        "Equity curve",
        "Drawdown",
        "Return per year",
        "Strategy vs buy and hold",
        "Per year",
        "Halves of the window",
        "Gap sensitivity",
        "Trades (times are candle open, UTC)",
    ):
        assert f"<h2>{section}" in text, section
    assert text.count("<svg") == 4
    assert "<script" not in text
    # No external assets: nothing loaded by src, href or CSS url().
    assert not re.search(r'(?:src|href)\s*=\s*["\']?https?:', text)
    assert not re.search(r"url\(\s*['\"]?https?:", text)
    assert "abc123" in text and "clean" in text
    assert "Start is only 2 days after the first candle" in text
    assert "Net PnL without top 1% (" in text
    assert "and without top 1% (" in text


def test_report_cli_writes_to_out(run_folder, tmp_path, capsys):
    out = tmp_path / "reports" / "r.html"
    assert main(["report", "--run", str(run_folder), "--out", str(out)]) == 0
    assert out.exists()
    assert "Report written" in capsys.readouterr().out
