"""Experiment log: append-only, variant counting and the seen-window overlap."""

import pytest

from conftest import random_walk
from real_edge_backtest.cli import main
from real_edge_backtest.experiments import (
    append,
    param_hash,
    read_log,
    seen_window,
    variant_count,
)


def entry(family, start, end, **params):
    params = {"ema_length": 9, **params, "start": start, "end": end}
    return {
        "family": family,
        "param_hash": param_hash(params),
        "params": params,
        "window": {"start": start, "end": end},
    }


def test_append_never_rewrites_earlier_lines(tmp_path):
    path = tmp_path / "experiments" / "log.jsonl"
    append(path, entry("a", "2020-01-01", "2021-01-01"))
    first = path.read_bytes()
    append(path, entry("a", "2021-01-01", "2022-01-01"))
    append(path, entry("b", "2020-01-01", "2022-01-01"))
    after = path.read_bytes()
    assert after.startswith(first)
    assert after.count(b"\n") == 3
    assert [e["family"] for e in read_log(path)] == ["a", "a", "b"]


def test_window_is_not_part_of_the_variant():
    assert param_hash({"x": 1, "start": "2020"}) == param_hash({"x": 1, "start": "2024"})
    assert param_hash({"x": 1}) != param_hash({"x": 2})


def test_variant_count_per_family():
    log = [
        entry("a", "2020-01-01", "2021-01-01", trend_length=21),
        entry("a", "2022-01-01", "2023-01-01", trend_length=21),  # same variant, other window
        entry("a", "2020-01-01", "2021-01-01", trend_length=50),
        entry("b", "2020-01-01", "2021-01-01", trend_length=21),
    ]
    assert variant_count(log, "a") == 2
    assert variant_count(log, "b") == 1


def test_seen_window_without_overlap():
    log = [entry("a", "2020-01-01", "2021-01-01"), entry("b", "2022-01-01", "2023-01-01")]
    seen = seen_window(log, "a", "2022-01-01", "2023-01-01")
    assert seen == {"runs": 0, "overlap_days": 0.0, "window_days": 365.0, "param_sets": 0}


def test_seen_window_partial_and_nested_overlaps_are_unioned():
    log = [
        entry("a", "2021-12-01", "2022-01-11", trend_length=21),  # 10 days inside
        entry("a", "2022-01-05", "2022-01-21", trend_length=50),  # 05 to 21 Jan, nested part
        entry("a", "2022-01-08", "2022-01-09", trend_length=21),  # fully nested
        entry("a", "2022-03-01", "2022-03-03", trend_length=21),  # 2 more days
        entry("a", "2023-01-01", "2023-02-01", trend_length=99),  # outside
    ]
    seen = seen_window(log, "a", "2022-01-01", "2023-01-01")
    # union: 1 to 21 Jan (20 days) + 1 to 3 Mar (2 days)
    assert seen["runs"] == 4
    assert seen["overlap_days"] == 22.0
    assert seen["param_sets"] == 2


def test_touching_windows_do_not_overlap():
    log = [entry("a", "2021-01-01", "2022-01-01")]
    assert seen_window(log, "a", "2022-01-01", "2023-01-01")["runs"] == 0


@pytest.fixture
def config_file(tmp_path):
    data_dir = tmp_path / "data"
    target = data_dir / "spot" / "klines" / "TEST" / "1h.parquet"
    target.parent.mkdir(parents=True)
    random_walk(1500, 7).to_parquet(target)
    path = tmp_path / "run.toml"
    path.write_text(
        f"""name = "case"
[data]
symbol = "TEST"
interval = "1h"
data_dir = "{data_dir.as_posix()}"
[strategy]
name = "ema_vwap"
[strategy.params]
start = "2025-01-03T00:00:00Z"
end = "2025-02-20T00:00:00Z"
[output]
runs_dir = "{(tmp_path / "runs").as_posix()}"
experiment_log = "{(tmp_path / "log.jsonl").as_posix()}"
""",
        encoding="utf-8",
    )
    return path


def test_run_appends_and_reports_seen_window(config_file, tmp_path, capsys):
    assert main(["run", "--config", str(config_file)]) == 0
    assert "unseen by earlier runs" in capsys.readouterr().out
    assert main(["run", "--config", str(config_file)]) == 0
    out = capsys.readouterr().out
    assert "1 earlier runs overlap" in out
    assert "1 parameter sets of ema_vwap" in out
    log = read_log(tmp_path / "log.jsonl")
    assert len(log) == 2
    assert log[1]["metrics"]["trades"] == log[0]["metrics"]["trades"] > 0
    assert log[1]["git_commit"]
