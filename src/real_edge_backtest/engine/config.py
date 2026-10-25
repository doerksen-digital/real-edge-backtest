"""Run configuration, read from TOML with the standard library."""

import tomllib
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Any

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
    runs_dir: Path = Path("runs")
    source_text: str = ""


def _decimal(value: Any) -> Decimal:
    """Decimal from a TOML value. Strings are exact; floats go through str() to drop noise."""
    return Decimal(value) if isinstance(value, str) else Decimal(str(value))


def load_config(path: Path) -> RunConfig:
    text = path.read_text(encoding="utf-8")
    raw = tomllib.loads(text)
    data = raw.get("data", {})
    broker = raw.get("broker", {})
    strategy = raw.get("strategy", {})
    defaults = BrokerConfig()
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
        runs_dir=Path(raw.get("output", {}).get("runs_dir", "runs")),
        source_text=text,
    )
