"""Run comparison: matched by side and entry time, and the fate of A's best trades in B."""

import pandas as pd

from conftest import random_walk
from real_edge_backtest.analysis.compare import diff_trades, top_fate
from real_edge_backtest.analysis.metrics import Run, load_run
from real_edge_backtest.cli import main
from real_edge_backtest.engine import Backtest, BrokerConfig
from real_edge_backtest.engine.results import write_run
from real_edge_backtest.strategies.ema_vwap import EmaVwap

META = {"broker": {"initial_capital": "1000"}, "criteria": {}}


def frame(rows):
    t = pd.DataFrame(
        rows, columns=["number", "side", "entry_time", "exit_time", "exit_price", "net_pnl"]
    )
    for column in ("entry_time", "exit_time"):
        t[column] = pd.to_datetime(t[column], utc=True)
    t["exit_comment"] = "x"
    return t


A = frame(
    [
        (1, "long", "2026-01-01 00:00", "2026-01-01 05:00", 110.0, 100.0),
        (2, "short", "2026-01-02 00:00", "2026-01-02 05:00", 90.0, -10.0),
        (3, "long", "2026-01-03 00:00", "2026-01-03 05:00", 120.0, 50.0),
        (4, "short", "2026-01-04 00:00", "2026-01-04 05:00", 80.0, 80.0),
    ]
)
B = frame(
    [
        (1, "long", "2026-01-01 00:00", "2026-01-01 05:00", 110.0, 100.0),  # same exit
        (2, "short", "2026-01-02 00:00", "2026-01-02 06:00", 95.0, -12.0),  # exit changed
        (3, "long", "2026-01-02 23:00", "2026-01-03 10:00", 125.0, 60.0),  # covers A#3
        (4, "short", "2026-01-05 00:00", "2026-01-05 05:00", 70.0, 30.0),  # appeared
    ]
)


def test_diff_trades():
    d = diff_trades(A, B)
    assert list(d.disappeared["number"]) == [3, 4]
    assert list(d.appeared["number"]) == [3, 4]
    assert list(d.changed["number_a"]) == [2] and list(d.changed["number_b"]) == [2]
    assert d.same_exit == 1


def test_top_fate_of_a_best_trades():
    # returns on 1,000: #1 +10%, #4 80/1140 = 7.0%, #3 50/1090 = 4.6%; top 75% = 3 trades
    fate = top_fate(Run(META, A, None), Run(META, B, None), 75).set_index("number_a")
    assert list(fate.index) == [1, 4, 3]
    assert fate.loc[1, "outcome"] == "in B, same exit"
    assert fate.loc[4, "outcome"] == "missing in B"
    assert fate.loc[4, "note"] == "B was flat at that entry"
    assert fate.loc[3, "note"] == "B was in trade #3 (long, entered 2026-01-02 23:00)"
    fate = top_fate(Run(META, A, None), Run(META, B.assign(exit_price=111.0), None), 1)
    assert list(fate["outcome"]) == ["in B, exit changed"]


def test_compare_cli_writes_html(tmp_path):
    meta = {
        "name": "case",
        "symbol": "TEST",
        "window": {"start": "2025-01-03T00:00:00Z", "end": "2025-02-20T00:00:00Z"},
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
    }
    folders = []
    for stop in (2.0, 1.0):
        params = {**meta["window"], "stop_atr": stop}
        result = Backtest(random_walk(1500, 7), EmaVwap, BrokerConfig(), params).run()
        folders.append(write_run(result, tmp_path / str(stop), "case", "", meta))
    out = tmp_path / "compare.html"
    assert main(["report", "--compare", *map(str, folders), "--out", str(out)]) == 0
    text = out.read_text(encoding="utf-8")
    for section in ("Pass criteria", "Metrics", "A's top 1% winners in B", "Trades"):
        assert f"<h2>{section}</h2>" in text, section
    a, b = load_run(folders[0]), load_run(folders[1])
    d = diff_trades(a.trades, b.trades)
    assert len(d.disappeared) + len(d.changed) + d.same_exit == len(a.trades)
    assert len(d.changed) > 0
    assert f"Disappeared: in A, not in B ({len(d.disappeared)})" in text
    assert "<script" not in text
