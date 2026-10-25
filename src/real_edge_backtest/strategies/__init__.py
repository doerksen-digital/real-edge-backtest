"""Strategies, one module each, registered by config name."""

from real_edge_backtest.engine.strategy import Strategy
from real_edge_backtest.strategies.ema_vwap import EmaVwap

STRATEGIES: dict[str, type[Strategy]] = {"ema_vwap": EmaVwap}

__all__ = ["STRATEGIES", "EmaVwap"]
