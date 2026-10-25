"""experiments/log.jsonl: one JSON line per run, committed to the repository.

The file is only ever opened in append mode; earlier lines are never rewritten. The log never
blocks a run. It records which windows a strategy family has already been tested on, so a
report can say whether its window is unseen (a soft lockbox).

- family: the strategy name
- variant: a distinct strategy parameter set, ignoring the window (start, end)
"""

import hashlib
import json
from pathlib import Path
from typing import Any

import pandas as pd

WINDOW_KEYS = ("start", "end")


def param_hash(params: dict[str, Any]) -> str:
    """Fingerprint of a parameter set without its window."""
    core = {k: v for k, v in params.items() if k not in WINDOW_KEYS}
    text = json.dumps(core, sort_keys=True, default=str)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def read_log(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line.strip()]


def append(path: Path, entry: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(entry, sort_keys=True, default=str) + "\n")


def make_entry(meta: dict[str, Any], metrics: dict[str, Any], run_folder: str) -> dict[str, Any]:
    """One log line from a run's run.json content and its key metrics."""
    prov = meta.get("provenance", {})
    return {
        "timestamp_utc": pd.Timestamp.now(tz="UTC").isoformat(timespec="seconds"),
        "source": "engine",
        "family": meta["strategy"],
        "name": meta["name"],
        "git_commit": prov.get("commit"),
        "git_dirty": prov.get("dirty"),
        "config_sha256": prov.get("config_sha256"),
        "data_sha256": prov.get("data_sha256"),
        "params": meta["params"],
        "param_hash": param_hash(meta["params"]),
        "window": meta["window"],
        "symbol": meta["symbol"],
        "interval": meta["interval"],
        "fill_model": meta["broker"]["fill_model"],
        "commission_pct": meta["broker"]["commission_pct"],
        "slippage_ticks": meta["broker"]["slippage_ticks"],
        "sizing_mode": meta.get("sizing", {}).get("mode", "percent_equity"),
        "holdout": bool(meta.get("holdout", False)),
        "metrics": metrics,
        "run_folder": run_folder,
    }


def variant_count(entries: list[dict[str, Any]], family: str) -> int:
    return len({e["param_hash"] for e in entries if e["family"] == family})


def _utc(value: str) -> pd.Timestamp:
    ts = pd.Timestamp(value)
    return ts.tz_localize("UTC") if ts.tzinfo is None else ts.tz_convert("UTC")


def seen_window(entries: list[dict[str, Any]], family: str, start: str, end: str) -> dict[str, Any]:
    """Earlier runs of `family` whose window overlaps [start, end): how many, on how many days
    of the requested window (union of the overlaps), and with how many parameter sets."""
    lo, hi = _utc(start), _utc(end)
    overlaps, hashes = [], set()
    for e in entries:
        if e["family"] != family:
            continue
        a = max(lo, _utc(e["window"]["start"]))
        b = min(hi, _utc(e["window"]["end"]))
        if a < b:
            overlaps.append((a, b))
            hashes.add(e["param_hash"])
    covered = pd.Timedelta(0)
    current_start = current_end = None
    for a, b in sorted(overlaps):
        if current_end is None or a > current_end:
            if current_end is not None:
                covered += current_end - current_start
            current_start, current_end = a, b
        else:
            current_end = max(current_end, b)
    if current_end is not None:
        covered += current_end - current_start
    return {
        "runs": len(overlaps),
        "overlap_days": covered / pd.Timedelta(days=1),
        "window_days": (hi - lo) / pd.Timedelta(days=1),
        "param_sets": len(hashes),
    }


def describe_seen(seen: dict[str, Any]) -> str:
    """One line for the run output and the report header. Overlaps under a day in hours."""
    if not seen.get("runs"):
        return "unseen: no earlier run of this strategy family overlaps the window"
    days = seen["overlap_days"]
    span = f"{days * 24:.0f} hours" if days < 1 else f"{days:.1f} days"
    return (
        f"seen: {seen['runs']} earlier runs overlap {span} of the {seen['window_days']:.1f}-day "
        f"window, with {seen['param_sets']} distinct parameter sets"
    )
