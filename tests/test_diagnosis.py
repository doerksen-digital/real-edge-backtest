"""Diagnosis tables render from a run folder and assign the 1% groups by percent return."""

from conftest import random_walk
from real_edge_backtest.analysis.diagnosis import load, main
from real_edge_backtest.analysis.metrics import top_pct_count
from real_edge_backtest.engine import Backtest, BrokerConfig
from real_edge_backtest.engine.results import write_run
from real_edge_backtest.strategies.ema_vwap import EmaVwap

PARAMS = {"start": "2025-01-10T00:00:00Z", "end": "2025-04-01T00:00:00Z"}
META = {
    "name": "case",
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
}


def test_diagnosis_renders(tmp_path):
    result = Backtest(random_walk(2400, 3), EmaVwap, BrokerConfig(), PARAMS).run()
    folder = write_run(result, tmp_path, "case", "", META)
    t = load(folder)
    n = top_pct_count(len(t), 1)
    assert (t["group"] == "top 1%").sum() == n and (t["group"] == "bottom 1%").sum() == n
    assert t.loc[t["group"] == "top 1%", "return"].min() >= t["return"].median()
    out = tmp_path / "diagnosis.md"
    assert main([str(folder), "--out", str(out)]) == 0
    text = out.read_text(encoding="utf-8")
    for heading in (
        "### Overview",
        "### Giveback",
        "### Where the losses come from",
        "### Recent crosses (chop)",
        "### Fees and move size per year",
        "### Entry features by quintile",
        "### Bin patterns in both halves",
        "### Distributions per group",
    ):
        assert heading in text, heading
    assert "(few)" in text
