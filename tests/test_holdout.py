"""Holdout guard: no strategy run on ETHUSDT or SOLUSDT without --holdout (synthetic data)."""

import json

import pytest

from conftest import random_walk
from real_edge_backtest.cli import main
from real_edge_backtest.experiments import read_log
from real_edge_backtest.holdout import HoldoutError, check_holdout
from real_edge_backtest.report.html import write_report


def test_check_holdout():
    assert check_holdout("BTCUSDT", False) is False
    assert check_holdout("ethusdt", True) is True
    for symbol in ("ETHUSDT", "SOLUSDT", "solusdt"):
        with pytest.raises(HoldoutError, match="--holdout"):
            check_holdout(symbol, False)


@pytest.fixture
def holdout_config(tmp_path):
    """Synthetic candles stored under a holdout symbol name. No real ETH data is used."""
    data_dir = tmp_path / "data"
    target = data_dir / "spot" / "klines" / "ETHUSDT" / "1h.parquet"
    target.parent.mkdir(parents=True)
    random_walk(1500, 7).to_parquet(target)
    path = tmp_path / "run.toml"
    path.write_text(
        f"""name = "holdout_case"
[data]
symbol = "ETHUSDT"
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


def test_run_on_holdout_is_refused_without_flag(holdout_config, tmp_path, capsys):
    assert main(["run", "--config", str(holdout_config)]) == 1
    err = capsys.readouterr().err
    assert "ETHUSDT is holdout data" in err and "--holdout" in err
    assert not (tmp_path / "runs").exists()
    assert not (tmp_path / "log.jsonl").exists()


def test_run_on_holdout_with_flag_is_marked(holdout_config, tmp_path, capsys):
    assert main(["run", "--config", str(holdout_config), "--holdout"]) == 0
    assert capsys.readouterr().out.startswith("HOLDOUT RUN: ETHUSDT")
    (entry,) = read_log(tmp_path / "log.jsonl")
    assert entry["holdout"] is True
    (folder,) = (tmp_path / "runs").iterdir()
    assert json.loads((folder / "run.json").read_text(encoding="utf-8"))["holdout"] is True
    text = write_report(folder).read_text(encoding="utf-8")
    assert '<div class="holdout">HOLDOUT RUN: ETHUSDT' in text
