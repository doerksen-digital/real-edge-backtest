"""Simulated broker: positions, fills, commission, equity and the trade list.

Exact arithmetic: prices are integer ticks, quantities integer lots, money is Decimal. Floats
appear only when results are written out.

Rules (TradingView broker emulator, Pine v6 docs):
- market orders fill at the bar close (process_orders_on_close) plus slippage against the trader
- stop orders fill at their level, or at the open after a gap, plus slippage against the trader
- commission is a percent of each fill's value
- an entry against an open position closes it and opens the new one in a single fill
- pyramiding 0: an entry in the direction of the open position is rejected
- equity = initial capital + net profit of closed trades + open profit
"""

from dataclasses import dataclass, field
from decimal import Decimal

import pandas as pd

from real_edge_backtest.engine.config import BrokerConfig
from real_edge_backtest.engine.fills import FILL_MODELS, Bar, PriceOrder


@dataclass
class Trade:
    number: int
    side: int  # +1 long, -1 short
    lots: int
    entry_index: int
    entry_time: pd.Timestamp
    entry_price: int
    entry_comment: str
    entry_commission: Decimal
    exit_index: int | None = None
    exit_time: pd.Timestamp | None = None
    exit_price: int | None = None
    exit_comment: str = ""
    exit_commission: Decimal = Decimal(0)
    gross_pnl: Decimal = Decimal(0)

    @property
    def commission(self) -> Decimal:
        return self.entry_commission + self.exit_commission

    @property
    def net_pnl(self) -> Decimal:
        return self.gross_pnl - self.commission


@dataclass
class Broker:
    config: BrokerConfig
    net_profit: Decimal = Decimal(0)
    trades: list[Trade] = field(default_factory=list)
    open_trade: Trade | None = None
    orders: dict[str, PriceOrder] = field(default_factory=dict)

    # Bar context, set by the backtest loop before any order is placed.
    index: int = 0
    time: pd.Timestamp | None = None
    bar: Bar | None = None

    @property
    def position(self) -> int:
        """Signed position in lots."""
        return 0 if self.open_trade is None else self.open_trade.side * self.open_trade.lots

    # Money helpers -------------------------------------------------------------------------

    def value(self, lots: int, price: int) -> Decimal:
        """Cash value of a fill."""
        cfg = self.config
        return lots * cfg.lot_size * price * cfg.tick_size * cfg.point_value

    def commission(self, lots: int, price: int) -> Decimal:
        return self.value(lots, price) * self.config.commission_rate

    def open_profit(self, price: int) -> Decimal:
        trade = self.open_trade
        if trade is None:
            return Decimal(0)
        return trade.side * self.value(trade.lots, price - trade.entry_price)

    def equity(self, price: int) -> Decimal:
        return self.config.initial_capital + self.net_profit + self.open_profit(price)

    def _slipped(self, price: int, side: int) -> int:
        return price + side * self.config.slippage_ticks

    # Position changes ----------------------------------------------------------------------

    def _close_trade(self, price: int, lots: int, comment: str) -> None:
        trade = self.open_trade
        assert trade is not None and lots == trade.lots
        trade.exit_index = self.index
        trade.exit_time = self.time
        trade.exit_price = price
        trade.exit_comment = comment
        trade.exit_commission = self.commission(lots, price)
        trade.gross_pnl = trade.side * self.value(lots, price - trade.entry_price)
        self.net_profit += trade.net_pnl
        self.open_trade = None
        self.orders.clear()

    def _open_trade(self, side: int, lots: int, price: int, comment: str) -> None:
        self.open_trade = Trade(
            number=len(self.trades) + 1,
            side=side,
            lots=lots,
            entry_index=self.index,
            entry_time=self.time,
            entry_price=price,
            entry_comment=comment,
            entry_commission=self.commission(lots, price),
        )
        self.trades.append(self.open_trade)

    # Commands used by strategies -----------------------------------------------------------

    def entry(self, side: int, lots: int, comment: str) -> bool:
        """Market entry at the bar close. Reverses an opposite position in the same fill."""
        assert self.bar is not None
        if lots <= 0 or (self.open_trade and self.open_trade.side == side):
            return False
        price = self._slipped(self.bar.close, side)
        if self.open_trade:
            self._close_trade(price, self.open_trade.lots, comment)
        self._open_trade(side, lots, price, comment)
        return True

    def close(self, comment: str) -> bool:
        """Market exit of the whole position at the bar close."""
        assert self.bar is not None
        if self.open_trade is None:
            return False
        price = self._slipped(self.bar.close, -self.open_trade.side)
        self._close_trade(price, self.open_trade.lots, comment)
        return True

    def exit_stop(self, order_id: str, ticks: int, comment: str) -> None:
        """Stop exit `ticks` from the entry fill price, against the position (exit loss)."""
        trade = self.open_trade
        if trade is None:
            return
        level = trade.entry_price - trade.side * ticks
        self.orders[order_id] = PriceOrder(order_id, "stop", -trade.side, level, comment)

    def cancel(self, order_id: str) -> None:
        self.orders.pop(order_id, None)

    # Called by the backtest loop -----------------------------------------------------------

    def process_price_orders(self) -> None:
        """Fill at most one exit order inside the current bar, before the close logic runs."""
        assert self.bar is not None
        if self.open_trade is None or not self.orders:
            return
        fill = FILL_MODELS[self.config.fill_model](self.bar, list(self.orders.values()))
        if fill is None:
            return
        order, trigger = fill
        price = self._slipped(trigger, order.side) if order.kind == "stop" else trigger
        self._close_trade(price, self.open_trade.lots, order.comment)
