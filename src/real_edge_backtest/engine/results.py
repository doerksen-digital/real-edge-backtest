"""Summary statistics and run output files. No report code: other tools read these files."""

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pandas as pd

from real_edge_backtest.engine.backtest import Result


@dataclass(frozen=True)
class Summary:
    trades: int
    winners: int
    win_rate: float
    profit_factor: float
    net_pnl: Decimal
    max_drawdown: Decimal


def summarize(result: Result) -> Summary:
    """Closed trades only. Profit factor = sum of winning net PnL / -sum of losing net PnL.
    Max drawdown = largest peak-to-trough fall of the close-to-close equity curve."""
    closed = result.closed_trades
    wins = [t.net_pnl for t in closed if t.net_pnl > 0]
    losses = [t.net_pnl for t in closed if t.net_pnl < 0]
    gross_win = sum(wins, Decimal(0))
    gross_loss = -sum(losses, Decimal(0))
    peak = None
    drawdown = Decimal(0)
    for value in result.equity["equity"]:
        peak = value if peak is None or value > peak else peak
        drawdown = max(drawdown, peak - value)
    return Summary(
        trades=len(closed),
        winners=len(wins),
        win_rate=len(wins) / len(closed) if closed else 0.0,
        profit_factor=float(gross_win / gross_loss) if gross_loss else float("inf"),
        net_pnl=sum((t.net_pnl for t in closed), Decimal(0)),
        max_drawdown=drawdown,
    )


def trades_frame(result: Result) -> pd.DataFrame:
    cfg = result.broker
    rows = []
    for t in result.trades:
        rows.append(
            {
                "number": t.number,
                "side": "long" if t.side > 0 else "short",
                "entry_time": t.entry_time,
                "entry_price": float(t.entry_price * cfg.tick_size),
                "exit_time": t.exit_time,
                "exit_price": None if t.exit_price is None else float(t.exit_price * cfg.tick_size),
                "qty": float(t.lots * cfg.lot_size),
                "entry_comment": t.entry_comment,
                "exit_comment": t.exit_comment,
                "gross_pnl": float(t.gross_pnl),
                "commission": float(t.commission),
                "net_pnl": float(t.net_pnl),
                "touches_gap": result.touches_gap(t),
                "sizing_capped": t.sizing_capped,
                "exit_kind": t.exit_kind,
                "both_in_bar": t.both_in_bar,
            }
        )
    return pd.DataFrame(rows)


def write_run(
    result: Result, runs_dir: Path, name: str, config_text: str, meta: dict | None = None
) -> Path:
    """trades.csv, trades_enriched.csv (entry features and excursions per trade), equity.csv
    (every candle of the dataset, with close time, open, close, the position after the bar and
    the strategy's bar columns), config.toml and run.json (meta: window, settings,
    provenance)."""
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    folder = runs_dir / f"{stamp}-{name}"
    suffix = 1
    while folder.exists():  # two runs in the same second
        suffix += 1
        folder = runs_dir / f"{stamp}-{name}-{suffix}"
    folder.mkdir(parents=True, exist_ok=False)
    trades_frame(result).to_csv(folder / "trades.csv", index=False)
    if result.enriched is not None:
        result.enriched.to_csv(folder / "trades_enriched.csv", index=False)
    equity = result.equity.assign(equity=result.equity["equity"].map(float))
    equity.to_csv(folder / "equity.csv", index=False)
    (folder / "config.toml").write_text(config_text, encoding="utf-8")
    text = json.dumps(meta or {}, indent=2, default=str)
    (folder / "run.json").write_text(text + "\n", encoding="utf-8")
    return folder
