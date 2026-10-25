"""Sweeps: each grid point is a logged run, at most 2 parameters, and a plain run keeps its
config hash."""

import hashlib
import json
from pathlib import Path

import pytest

from conftest import random_walk
from real_edge_backtest.cli import main
from real_edge_backtest.engine import load_config
from real_edge_backtest.engine.config import apply_overrides
from real_edge_backtest.experiments import read_log
from real_edge_backtest.runner import run_metadata
from real_edge_backtest.sweep import load_spec

ROOT = Path(__file__).resolve().parents[1]
FULL = ROOT / "configs" / "ema_vwap_full.toml"
FULL_SHA256 = "79aea06a9eda99a292ec41adb58373aeb14bab8a273d7f9b53b96c4a7eeb1e3d"
REFERENCE_RUN = ROOT / "runs" / "20261025T035823Z-ema_vwap_full" / "run.json"


def test_plain_run_config_hash_is_unchanged():
    meta = run_metadata(load_config(FULL))
    assert meta["provenance"]["config_sha256"] == FULL_SHA256
    assert hashlib.sha256(FULL.read_bytes()).hexdigest() == FULL_SHA256
    assert "overrides" not in meta


@pytest.mark.skipif(not REFERENCE_RUN.exists(), reason="reference run folder is local only")
def test_plain_run_config_hash_matches_reference_run():
    recorded = json.loads(REFERENCE_RUN.read_text(encoding="utf-8"))["provenance"]
    meta = run_metadata(load_config(FULL))
    assert meta["provenance"]["config_sha256"] == recorded["config_sha256"]


def test_overrides_change_params_and_hash():
    config = load_config(FULL, {"strategy.params.vwap_bars": 30})
    meta = run_metadata(config)
    assert meta["params"]["vwap_bars"] == 30
    assert meta["overrides"] == {"strategy.params.vwap_bars": 30}
    assert meta["provenance"]["config_sha256"] != FULL_SHA256


def test_override_of_a_missing_section_is_rejected():
    with pytest.raises(ValueError, match="does not exist"):
        apply_overrides({"strategy": {"params": {}}}, {"strategy.parms.x": 1})
    assert apply_overrides({"a": [{"b": 1}]}, {"a.0.b": 2}) == {"a": [{"b": 2}]}


BASE = """name = "case"
[data]
symbol = "{symbol}"
interval = "1h"
data_dir = "{data_dir}"
[strategy]
name = "ema_vwap"
[strategy.params]
stop_atr = 2.0
start = "2025-01-03T00:00:00Z"
end = "2025-02-20T00:00:00Z"
[output]
runs_dir = "{runs_dir}"
experiment_log = "{log}"
"""

SPEC = """id = "T1"
base = "{base}"
[grid]
"strategy.params.stop_atr" = [1.5, 2.5]
"""


def make_spec(tmp_path: Path, symbol: str = "TEST") -> Path:
    data_dir = tmp_path / "data"
    target = data_dir / "spot" / "klines" / symbol / "1h.parquet"
    target.parent.mkdir(parents=True)
    random_walk(1500, 7).to_parquet(target)
    base = tmp_path / "base.toml"
    base.write_text(
        BASE.format(
            symbol=symbol,
            data_dir=data_dir.as_posix(),
            runs_dir=(tmp_path / "runs").as_posix(),
            log=(tmp_path / "log.jsonl").as_posix(),
        ),
        encoding="utf-8",
    )
    path = tmp_path / "sweep.toml"
    path.write_text(SPEC.format(base=base.as_posix()), encoding="utf-8")
    return path


def test_sweep_runs_and_logs_every_point(tmp_path, capsys):
    assert main(["sweep", "--spec", str(make_spec(tmp_path))]) == 0
    out = capsys.readouterr().out
    assert "stop_atr=1.5" in out and "stop_atr=2.5" in out and "PF net" in out
    log = read_log(tmp_path / "log.jsonl")
    assert [e["params"]["stop_atr"] for e in log] == [1.5, 2.5]
    assert len({e["param_hash"] for e in log}) == 2
    (folder,) = (tmp_path / "runs" / "sweeps").iterdir()
    table = (folder / "sweep.csv").read_text(encoding="utf-8").splitlines()
    assert len(table) == 3 and table[0].startswith("strategy.params.stop_atr,profit_factor")
    runs = [p for p in (tmp_path / "runs").iterdir() if p.name != "sweeps"]
    assert len(runs) == 2 and all("-T1-stop_atr=" in p.name for p in runs)


def test_sweep_rejects_more_than_two_parameters(tmp_path):
    path = tmp_path / "s.toml"
    path.write_text(
        'id = "X"\nbase = "b.toml"\n[grid]\n"a.b" = [1]\n"a.c" = [1]\n"a.d" = [1]\n',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="1 to 2 parameters"):
        load_spec(path)


def test_sweep_on_holdout_is_refused(tmp_path, capsys):
    assert main(["sweep", "--spec", str(make_spec(tmp_path, "SOLUSDT"))]) == 1
    assert "SOLUSDT is holdout data" in capsys.readouterr().err
    assert not (tmp_path / "log.jsonl").exists()


def test_sweep_set_applies_to_every_point(tmp_path):
    path = make_spec(tmp_path)
    text = path.read_text(encoding="utf-8").replace(
        "[grid]", '[set]\n"strategy.params.direction" = "Long only"\n[grid]'
    )
    path.write_text(text, encoding="utf-8")
    assert main(["sweep", "--spec", str(path)]) == 0
    log = read_log(tmp_path / "log.jsonl")
    assert [e["params"]["direction"] for e in log] == ["Long only", "Long only"]
    run = sorted(p for p in (tmp_path / "runs").iterdir() if p.name != "sweeps")[0]
    meta = json.loads((run / "run.json").read_text(encoding="utf-8"))
    assert meta["overrides"] == {
        "strategy.params.direction": "Long only",
        "strategy.params.stop_atr": 1.5,
    }


def test_sweep_rejects_a_key_in_set_and_grid(tmp_path):
    path = tmp_path / "s.toml"
    path.write_text('id = "X"\nbase = "b.toml"\n[set]\n"a.b" = 1\n[grid]\n"a.b" = [1]\n', "utf-8")
    with pytest.raises(ValueError, match="both in"):
        load_spec(path)
