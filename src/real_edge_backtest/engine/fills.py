"""Fill models for price orders (stops and limits) inside one bar.

Prices are integer ticks. Both models fill an order that the open already passed (a gap) at the
open, as TradingView documents: "Rather than filling the order at the specified price in that
case, the emulator fills the order at the opening price".

- tradingview: TradingView's documented bar path. If the open is nearer the high than the low,
  the price moves open, high, low, close, otherwise open, low, high, close. Orders fill in the
  order the path reaches them.
- pessimistic: any stop the bar's range reaches fills before any limit, whatever the path.

With a single stop per position, as in ema_vwap, both models give the same fills. They differ
once a stop and a target are both inside one bar.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Bar:
    open: int
    high: int
    low: int
    close: int


@dataclass
class PriceOrder:
    """An exit order. side is the order direction: -1 sells (exits a long), +1 buys."""

    id: str
    kind: str  # "stop" or "limit"
    side: int
    level: int
    comment: str


def _triggered_at(order: PriceOrder, price: int) -> bool:
    if order.kind == "stop":
        return price <= order.level if order.side < 0 else price >= order.level
    return price >= order.level if order.side < 0 else price <= order.level


def _gap_fill(bar: Bar, orders: list[PriceOrder]) -> tuple[PriceOrder, int] | None:
    for order in orders:
        if _triggered_at(order, bar.open):
            return order, bar.open
    return None


def tradingview_fill(bar: Bar, orders: list[PriceOrder]) -> tuple[PriceOrder, int] | None:
    gap = _gap_fill(bar, orders)
    if gap:
        return gap
    if bar.high - bar.open < bar.open - bar.low:
        path = [bar.open, bar.high, bar.low, bar.close]
    else:
        path = [bar.open, bar.low, bar.high, bar.close]
    for start, end in zip(path, path[1:], strict=False):
        low, high = min(start, end), max(start, end)
        reached = [o for o in orders if low <= o.level <= high]
        if reached:
            first = min(reached, key=lambda o: abs(o.level - start))
            return first, first.level
    return None


def pessimistic_fill(bar: Bar, orders: list[PriceOrder]) -> tuple[PriceOrder, int] | None:
    gap = _gap_fill(bar, orders)
    if gap:
        return gap
    for kind in ("stop", "limit"):
        for order in orders:
            if order.kind == kind and bar.low <= order.level <= bar.high:
                return order, order.level
    return None


FILL_MODELS = {"tradingview": tradingview_fill, "pessimistic": pessimistic_fill}
