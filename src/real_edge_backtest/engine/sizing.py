"""Position sizing modes. All in exact fractions, results in whole lots.

- percent_equity: position_pct of equity, minus a fee reserve (TradingView's percent of
  equity; the default and the parity setting)
- fixed_risk: lose risk_pct of equity if the stop fills at its level
  (lots = risk / (stop distance per lot))
- fixed_notional: a fixed USD amount per trade

fixed_risk and fixed_notional are capped at 100% of equity with the fee reserve (spot, no
leverage). A capped entry is marked on the trade.
"""

import math
from dataclasses import dataclass
from decimal import Decimal
from fractions import Fraction

SIZING_MODES = ("percent_equity", "fixed_risk", "fixed_notional")


@dataclass(frozen=True)
class SizingConfig:
    mode: str = "percent_equity"
    risk_pct: Decimal = Decimal("1")
    notional_usd: Decimal = Decimal("1000")

    def __post_init__(self) -> None:
        if self.mode not in SIZING_MODES:
            raise ValueError(f"sizing mode must be one of {SIZING_MODES}, got {self.mode!r}")
        if self.risk_pct <= 0 or self.notional_usd <= 0:
            raise ValueError("risk_pct and notional_usd must be positive")

    def describe(self) -> dict[str, str]:
        if self.mode == "fixed_risk":
            return {"mode": self.mode, "risk_pct": str(self.risk_pct)}
        if self.mode == "fixed_notional":
            return {"mode": self.mode, "notional_usd": str(self.notional_usd)}
        return {"mode": self.mode}


def position_lots(
    equity: Decimal,
    position_pct: Decimal,
    fee_reserve_pct: Decimal,
    expected_fill: Decimal,
    point_value: Decimal,
    lot_size: Decimal,
) -> int:
    """floor(equity * pct/100 / (1 + fee/100) / (expected_fill * pointvalue) / lot) in lots.

    Computed with exact fractions, so a quotient that is an exact integer never floors to the
    integer below because of binary rounding.
    """
    equity = max(Decimal(0), equity)
    if expected_fill <= 0 or lot_size <= 0:
        return 0
    notional = (
        Fraction(equity) * Fraction(position_pct) / 100 / (1 + Fraction(fee_reserve_pct) / 100)
    )
    return math.floor(
        notional / (Fraction(expected_fill) * Fraction(point_value)) / Fraction(lot_size)
    )


def size(
    sizing: SizingConfig,
    equity: Decimal,
    position_pct: Decimal,
    fee_reserve_pct: Decimal,
    expected_fill: Decimal,
    point_value: Decimal,
    lot_size: Decimal,
    stop_distance: Decimal,
) -> tuple[int, bool]:
    """(lots, capped). stop_distance is the price distance from fill to stop (fixed_risk)."""
    if sizing.mode == "percent_equity":
        lots = position_lots(
            equity, position_pct, fee_reserve_pct, expected_fill, point_value, lot_size
        )
        return lots, False
    cap = position_lots(equity, Decimal(100), fee_reserve_pct, expected_fill, point_value, lot_size)
    if sizing.mode == "fixed_risk":
        if stop_distance <= 0:
            raise ValueError("fixed_risk sizing needs a stop")
        risk = Fraction(max(Decimal(0), equity)) * Fraction(sizing.risk_pct) / 100
        per_lot = Fraction(stop_distance) * Fraction(point_value) * Fraction(lot_size)
        wanted = math.floor(risk / per_lot)
    else:
        per_lot = Fraction(expected_fill) * Fraction(point_value) * Fraction(lot_size)
        wanted = math.floor(Fraction(sizing.notional_usd) / per_lot)
    return (cap, True) if wanted > cap else (wanted, False)
