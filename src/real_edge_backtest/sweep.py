"""Parameter sweeps: one hypothesis run over the parameter values fixed in its spec file.

A spec (TOML) names the hypothesis, the base run config and a grid of at most two parameters,
each a dotted key into the config with its values, written down before the sweep runs:

    id = "H1"
    base = "configs/ema_vwap_full.toml"   # relative to the current directory
    [grid]
    "strategy.params.vwap_bars" = [18, 24, 30]

Every grid point is an ordinary logged run (run folder, experiment log line, variant count),
so a sweep cannot hide how many variants were tried. The plateau table shows the main
metrics per point and is written to <runs_dir>/sweeps/<UTC timestamp>-<id>/sweep.csv.
"""

import dataclasses
import itertools
import tomllib
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from real_edge_backtest.analysis.metrics import Analysis
from real_edge_backtest.engine import load_config
from real_edge_backtest.runner import execute

MAX_PARAMS = 2


@dataclass(frozen=True)
class SweepSpec:
    id: str
    base: Path
    grid: dict[str, list[Any]]
    source_text: str = ""

    @property
    def points(self) -> list[dict[str, Any]]:
        keys = list(self.grid)
        return [
            dict(zip(keys, values, strict=True))
            for values in itertools.product(*self.grid.values())
        ]


@dataclass
class SweepResult:
    table: pd.DataFrame
    path: Path


def load_spec(path: Path) -> SweepSpec:
    text = path.read_text(encoding="utf-8")
    raw = tomllib.loads(text)
    unknown = set(raw) - {"id", "base", "grid"}
    if unknown:
        raise ValueError(f"unknown sweep spec keys: {sorted(unknown)}")
    grid = raw.get("grid", {})
    if not 1 <= len(grid) <= MAX_PARAMS:
        raise ValueError(
            f"a sweep varies 1 to {MAX_PARAMS} parameters (research protocol), got {len(grid)}"
        )
    for key, values in grid.items():
        if not isinstance(values, list) or not values:
            raise ValueError(f"grid {key!r} needs a non-empty list of values")
    return SweepSpec(id=str(raw["id"]), base=Path(raw["base"]), grid=dict(grid), source_text=text)


def point_label(point: dict[str, Any]) -> str:
    return ", ".join(f"{key.split('.')[-1]}={value}" for key, value in point.items())


def plateau_row(point: dict[str, Any], a: Analysis, folder: Path) -> dict[str, Any]:
    return {
        **point,
        "profit_factor": a.stats["profit_factor"],
        "net_pnl": a.stats["net_pnl"],
        "trades": a.stats["trades"],
        "fees": a.costs["fees"],
        "max_drawdown_pct": a.max_drawdown[1],
        "first_half": a.halves[0]["net_pnl"],
        "second_half": a.halves[1]["net_pnl"],
        "passed": a.passed,
        "run": folder.as_posix(),
    }


def run_sweep(
    spec: SweepSpec, holdout: bool = False, progress: Callable[[str], None] | None = None
) -> SweepResult:
    rows, runs_dir = [], None
    for point in spec.points:
        config = load_config(spec.base, point)
        suffix = "-".join(f"{k.split('.')[-1]}={v}" for k, v in point.items())
        config = dataclasses.replace(config, name=f"{config.name}-{spec.id}-{suffix}")
        runs_dir = config.runs_dir
        run = execute(config, holdout=holdout)
        rows.append(plateau_row(point, run.analysis, run.folder))
        if progress:
            progress(f"  {point_label(point)}: {run.folder}")
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    folder = runs_dir / "sweeps" / f"{stamp}-{spec.id}"
    folder.mkdir(parents=True, exist_ok=False)
    table = pd.DataFrame(rows)
    table.to_csv(folder / "sweep.csv", index=False)
    (folder / "spec.toml").write_text(spec.source_text, encoding="utf-8")
    return SweepResult(table, folder / "sweep.csv")


def format_table(table: pd.DataFrame) -> str:
    """Plateau table for the terminal, one line per grid point."""
    params = [c for c in table.columns if "." in c]
    lines = [
        f"{'point':<32} {'PF net':>7} {'net PnL':>12} {'trades':>6} {'fees':>10} "
        f"{'max DD':>7} {'1st half':>11} {'2nd half':>11}  pass"
    ]
    for _, r in table.iterrows():
        label = point_label({p: r[p] for p in params})
        lines.append(
            f"{label:<32} {r['profit_factor']:>7.3f} {r['net_pnl']:>12,.2f} {r['trades']:>6} "
            f"{r['fees']:>10,.2f} {r['max_drawdown_pct']:>7.2%} {r['first_half']:>11,.2f} "
            f"{r['second_half']:>11,.2f}  {'yes' if r['passed'] else 'no'}"
        )
    return "\n".join(lines)
