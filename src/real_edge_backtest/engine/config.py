"""Run configuration, read from TOML with the standard library."""

import copy
import json
import tomllib
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Any

from real_edge_backtest.engine.sizing import SizingConfig

FILL_MODELS = ("tradingview", "pessimistic")


@dataclass(frozen=True)
class BrokerConfig:
    initial_capital: Decimal = Decimal("10000")
    commission_pct: Decimal = Decimal("0.05")
    slippage_ticks: int = 2
    tick_size: Decimal = Decimal("0.01")
    lot_size: Decimal = Decimal("0.00001")
    point_value: Decimal = Decimal("1")
    fill_model: str = "pessimistic"

    def __post_init__(self) -> None:
        if self.fill_model not in FILL_MODELS:
            raise ValueError(f"fill_model must be one of {FILL_MODELS}, got {self.fill_model!r}")

    @property
    def commission_rate(self) -> Decimal:
        return self.commission_pct / 100


@dataclass(frozen=True)
class RunConfig:
    name: str
    symbol: str
    interval: str
    data_dir: Path
    strategy: str
    params: dict[str, Any] = field(default_factory=dict)
    broker: BrokerConfig = field(default_factory=BrokerConfig)
    sizing: SizingConfig = field(default_factory=SizingConfig)
    min_gap_bars: int = 3  # [gaps]: gaps this long block entries until indicators recover
    runs_dir: Path = Path("runs")
    experiment_log: Path = Path("experiments/log.jsonl")
    criteria: dict[str, Any] = field(default_factory=dict)  # pass criteria, read by the report
    source_text: str = ""
    # Dotted-key overrides applied on top of source_text (sweeps); empty for a plain run.
    overrides: dict[str, Any] = field(default_factory=dict)

    @property
    def fingerprint_text(self) -> str:
        """The text config_sha256 is computed from: the config file itself for a plain run,
        plus the canonical JSON of the overrides for a sweep point."""
        if not self.overrides:
            return self.source_text
        return self.source_text + "\n# overrides\n" + json.dumps(self.overrides, sort_keys=True)


def _decimal(value: Any) -> Decimal:
    """Decimal from a TOML value. Strings are exact; floats go through str() to drop noise."""
    return Decimal(value) if isinstance(value, str) else Decimal(str(value))


def apply_overrides(raw: dict[str, Any], overrides: dict[str, Any]) -> dict[str, Any]:
    """A copy of the raw TOML dict with dotted keys set, e.g. "strategy.params.vwap_bars".
    A numeric part indexes a list ("strategy.filters.0.lookback"). Every part but the last
    must already exist, so a typo cannot create a new section."""
    raw = copy.deepcopy(raw)
    for key, value in overrides.items():
        *parents, last = key.split(".")
        node: Any = raw
        for part in parents:
            try:
                node = node[int(part)] if isinstance(node, list) else node[part]
            except (KeyError, IndexError, ValueError):
                raise ValueError(
                    f"override {key!r}: {part!r} does not exist in the config"
                ) from None
        if isinstance(node, list):
            node[int(last)] = value
        else:
            node[last] = value
    return raw


def load_config(path: Path, overrides: dict[str, Any] | None = None) -> RunConfig:
    text = path.read_text(encoding="utf-8")
    raw = tomllib.loads(text)
    if overrides:
        raw = apply_overrides(raw, overrides)
    return parse_config(raw, text, overrides or {})


def parse_config(raw: dict[str, Any], text: str, overrides: dict[str, Any]) -> RunConfig:
    data = raw.get("data", {})
    broker = raw.get("broker", {})
    strategy = raw.get("strategy", {})
    defaults = BrokerConfig()
    sizing = raw.get("sizing", {})
    sizing_defaults = SizingConfig()
    return RunConfig(
        name=raw["name"],
        symbol=data["symbol"].upper(),
        interval=data["interval"],
        data_dir=Path(data.get("data_dir", "data")),
        strategy=strategy["name"],
        params=dict(strategy.get("params", {})),
        broker=BrokerConfig(
            initial_capital=_decimal(broker.get("initial_capital", defaults.initial_capital)),
            commission_pct=_decimal(broker.get("commission_pct", defaults.commission_pct)),
            slippage_ticks=int(broker.get("slippage_ticks", defaults.slippage_ticks)),
            tick_size=_decimal(broker.get("tick_size", defaults.tick_size)),
            lot_size=_decimal(broker.get("lot_size", defaults.lot_size)),
            point_value=_decimal(broker.get("point_value", defaults.point_value)),
            fill_model=broker.get("fill_model", defaults.fill_model),
        ),
        sizing=SizingConfig(
            mode=sizing.get("mode", sizing_defaults.mode),
            risk_pct=_decimal(sizing.get("risk_pct", sizing_defaults.risk_pct)),
            notional_usd=_decimal(sizing.get("notional_usd", sizing_defaults.notional_usd)),
        ),
        min_gap_bars=int(raw.get("gaps", {}).get("min_gap_bars", 3)),
        runs_dir=Path(raw.get("output", {}).get("runs_dir", "runs")),
        experiment_log=Path(raw.get("output", {}).get("experiment_log", "experiments/log.jsonl")),
        criteria=dict(raw.get("criteria", {})),
        source_text=text,
        overrides=dict(overrides),
    )
