"""Strategies, one module each, registered by config name."""

from real_edge_backtest.engine.strategy import Strategy
from real_edge_backtest.strategies.ema_vwap import EmaVwap
from real_edge_backtest.strategies.ny_range import NyRange

STRATEGIES: dict[str, type[Strategy]] = {"ema_vwap": EmaVwap, "ny_range": NyRange}

__all__ = ["STRATEGIES", "EmaVwap", "NyRange"]
