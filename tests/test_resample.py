"""Higher timeframes: 4h candles from 1h, gaps kept, and a full run on 4h bars."""

import json

import pandas as pd
import pytest

from conftest import random_walk
from real_edge_backtest.cli import main
from real_edge_backtest.data.resample import resample_candles
from real_edge_backtest.experiments import read_log


def hourly(hours: list[int]) -> pd.DataFrame:
    times = pd.Timestamp("2026-01-01", tz="UTC") + pd.to_timedelta(hours, unit="h")
    values = [float(h) for h in hours]
    return pd.DataFrame(
        {
            "open_time": times,
            "open": [100 + v for v in values],
            "high": [200 + v for v in values],
            "low": [50 + v for v in values],
            "close": [101 + v for v in values],
            "volume": [1.0] * len(hours),
        }
    )


def test_resample_to_4h_keeps_partial_buckets_and_gaps():
    # bucket 00: hours 0-3; bucket 04: 4, 6, 7 (5 missing); bucket 08: nothing (a gap);
    # bucket 12: 12, 13 and the data ends, so it is dropped.
    out = resample_candles(hourly([0, 1, 2, 3, 4, 6, 7, 12, 13]), "1h", "4h")
    assert list(out["open_time"].dt.hour) == [0, 4]
    first, second = out.iloc[0], out.iloc[1]
    assert (first["open"], first["high"], first["low"], first["close"]) == (100, 203, 50, 104)
    assert first["volume"] == 4
    assert (second["open"], second["close"], second["volume"]) == (104, 108, 3)


def test_complete_last_bucket_is_kept():
    out = resample_candles(hourly(list(range(8))), "1h", "4h")
    assert list(out["open_time"].dt.hour) == [0, 4]


def test_timeframe_must_be_a_multiple_of_the_interval():
    with pytest.raises(ValueError, match="whole multiple"):
        resample_candles(hourly([0, 1]), "4h", "1h")
    with pytest.raises(ValueError, match="whole multiple"):
        resample_candles(hourly([0, 1]), "8h", "12h")


CONFIG = """name = "case"
[data]
symbol = "TEST"
interval = "1h"
{timeframe}
data_dir = "{data_dir}"
[strategy]
name = "ema_vwap"
[strategy.params]
vwap_bars = 6
start = "2025-01-08T00:00:00Z"
end = "2025-03-01T00:00:00Z"
[output]
runs_dir = "{runs_dir}"
experiment_log = "{log}"
"""


def test_run_on_4h_bars(tmp_path, capsys):
    data_dir = tmp_path / "data"
    target = data_dir / "spot" / "klines" / "TEST" / "1h.parquet"
    target.parent.mkdir(parents=True)
    random_walk(1500, 7).to_parquet(target)
    for tf in ("", 'timeframe = "4h"'):
        path = tmp_path / "run.toml"
        path.write_text(
            CONFIG.format(
                timeframe=tf,
                data_dir=data_dir.as_posix(),
                runs_dir=(tmp_path / "runs").as_posix(),
                log=(tmp_path / "log.jsonl").as_posix(),
            ),
            encoding="utf-8",
        )
        assert main(["run", "--config", str(path)]) == 0
    assert "TEST 4h from 1h" in capsys.readouterr().out
    plain, four = read_log(tmp_path / "log.jsonl")
    assert four["timeframe"] == "4h" and "timeframe" not in plain
    assert four["param_hash"] != plain["param_hash"]
    folder = sorted((tmp_path / "runs").iterdir())[-1]
    equity = pd.read_csv(folder / "equity.csv", parse_dates=["open_time", "time_close"])
    assert (equity["time_close"] - equity["open_time"] == pd.Timedelta(hours=4)).all()
    assert len(equity) == 375  # 1,500 hours
    assert json.loads((folder / "run.json").read_text(encoding="utf-8"))["timeframe"] == "4h"
