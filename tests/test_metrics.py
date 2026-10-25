"""Metrics on hand-built trade lists and equity curves. Expected values are computed by hand."""

import math

import pandas as pd
import pytest

from conftest import random_walk
from real_edge_backtest.analysis.metrics import (
    Criteria,
    Run,
    analyze,
    buy_and_hold,
    by_year,
    closed_trade_equity,
    compounded_without_top,
    halves,
    load_run,
    max_drawdown,
    pnl_without_top,
    time_in_market,
    top_pct_count,
    trade_returns,
    trade_stats,
    window_equity,
)
from real_edge_backtest.engine import Backtest, BrokerConfig
from real_edge_backtest.engine.results import summarize, write_run
from real_edge_backtest.strategies.ema_vwap import EmaVwap

T = pd.Timestamp


def trades(pnls, exits) -> pd.DataFrame:
    exit_times = pd.to_datetime(exits, utc=True)
    return pd.DataFrame(
        {
            "number": range(1, len(pnls) + 1),
            "entry_time": exit_times - pd.Timedelta(hours=5),
            "exit_time": exit_times,
            "net_pnl": [float(p) for p in pnls],
        }
    )


PNLS = [100, -50, 30, -20, 200]
EXITS = ["2024-03-01", "2024-09-01", "2025-02-01", "2025-06-01", "2025-11-01"]


def test_trade_stats():
    s = trade_stats(trades(PNLS, EXITS))
    assert s["trades"] == 5
    assert s["net_pnl"] == 260
    assert s["profit_factor"] == pytest.approx(330 / 70)
    assert s["expectancy"] == 52
    assert s["win_rate"] == 0.6
    assert s["average_win"] == 110
    assert s["average_loss"] == -35


def test_open_trade_is_ignored():
    t = trades([10, 5], ["2024-01-02", "2024-01-03"])
    t.loc[1, "exit_time"] = pd.NaT
    assert trade_stats(t)["trades"] == 1 and trade_stats(t)["net_pnl"] == 10


def test_profit_factor_without_losses_is_infinite():
    assert math.isinf(trade_stats(trades([10, 20], EXITS[:2]))["profit_factor"])


def test_pnl_without_top_winners():
    t = trades(PNLS, EXITS)
    assert pnl_without_top(t, 1) == 60  # 260 - 200
    assert pnl_without_top(t, 3) == -70  # 260 - 200 - 100 - 30
    assert pnl_without_top(t, 5) == -70  # only three winners exist


def test_halves_split_at_window_midpoint_by_exit():
    first, second = halves(
        trades(PNLS, EXITS), T("2024-01-01", tz="UTC"), T("2026-01-01", tz="UTC")
    )
    assert first["to"] == T("2024-12-31 12:00", tz="UTC")  # 731 days / 2
    assert (first["trades"], first["net_pnl"]) == (2, 50)
    assert (second["trades"], second["net_pnl"]) == (3, 210)


def test_closed_trade_drawdown():
    curve = closed_trade_equity(trades(PNLS, EXITS), 1000)
    assert list(curve) == [1100, 1050, 1080, 1060, 1260]
    assert max_drawdown(curve, 1000) == (50, pytest.approx(50 / 1100))


def test_drawdown_counts_from_starting_capital():
    assert max_drawdown(pd.Series([900.0, 950.0]), 1000) == (100, 0.1)


def test_by_year():
    window = pd.DataFrame(
        {
            "open_time": pd.to_datetime(
                ["2024-06-01 00:00", "2024-12-31 23:00", "2025-06-01 00:00", "2025-12-31 23:00"],
                utc=True,
            ),
            "equity": [1020.0, 1050.0, 1100.0, 1260.0],
        }
    )
    years = by_year(trades(PNLS, EXITS), window, 1000)
    assert list(years["year"]) == [2024, 2025]
    assert list(years["net_pnl"]) == [50, 210]
    assert list(years["trades"]) == [2, 3]
    assert years["return"].tolist() == pytest.approx([0.05, 1260 / 1050 - 1])


# Window cut ----------------------------------------------------------------------------------

BROKER = {
    "initial_capital": "1000",
    "commission_pct": "0.1",
    "slippage_ticks": 1,
    "tick_size": "0.01",
    "lot_size": "0.001",
    "point_value": "1",
    "fill_model": "pessimistic",
}


def equity_frame() -> pd.DataFrame:
    """Seven hourly bars. The window is bars 1 to 4 (closes 00:00 to 03:00). Bars 0, 5 and 6
    carry a huge equity value, a crash and an open position that must all be ignored."""
    open_time = pd.date_range("2024-12-31 22:00", periods=7, freq="h", tz="UTC")
    return pd.DataFrame(
        {
            "open_time": open_time,
            "time_close": open_time + pd.Timedelta(hours=1),
            "open": [50.0, 100.0, 100.0, 110.0, 90.0, 120.0, 10.0],
            "close": [50.0, 100.0, 110.0, 90.0, 120.0, 10.0, 1.0],
            "position": [0, 1, 1, 0, 0, 1, 1],
            "equity": [5000.0, 1000.0, 1100.0, 990.0, 990.0, 990.0, 100.0],
        }
    )


START, END = T("2025-01-01 00:00", tz="UTC"), T("2025-01-01 03:00", tz="UTC")


def test_window_equity_keeps_window_bars_only():
    window = window_equity(equity_frame(), START, END)
    assert list(window["time_close"].dt.hour) == [0, 1, 2, 3]
    # held: entered with an open position (position after the previous bar)
    assert list(window["held"]) == [False, True, True, False]
    assert time_in_market(window) == 0.5


def test_all_equity_metrics_use_the_window_only():
    run = Run(
        meta={"window": {"start": str(START), "end": str(END)}, "broker": BROKER, "criteria": {}},
        trades=trades([-10], ["2025-01-01 02:00"]),
        equity=equity_frame(),
    )
    a = analyze(run)
    # Full curve would give a 4,900 drawdown from 5,000 and a -90% return.
    assert a.max_drawdown == (110, pytest.approx(0.1))
    assert a.total_return == pytest.approx(-0.01)
    assert a.time_in_market == 0.5
    assert a.buy_and_hold["entry_price"] == 100.01  # bar 1's open, not bar 0's
    assert a.buy_and_hold["exit_price"] == 119.99  # bar 4's close, not bar 6's
    assert len(a.buy_and_hold["curve"]) == 4


def test_buy_and_hold_with_fees_and_slippage():
    window = window_equity(equity_frame(), START, END)
    bh = buy_and_hold(window, BROKER)
    # floor(1000 / 1.001 / 100.01 / 0.001) = floor(9989.01...) = 9989 lots = 9.989 BTC
    assert bh["lots"] == 9989
    cash = 1000 - 9.989 * 100.01 * 1.001
    final = cash + 9.989 * 119.99 * 0.999
    assert bh["final_equity"] == pytest.approx(final, abs=1e-9)
    assert bh["return"] == pytest.approx(final / 1000 - 1)
    # peak at bar 2 (close 110), trough at bar 3 (close 90)
    peak, trough = cash + 9.989 * 110, cash + 9.989 * 90
    assert bh["max_drawdown"] == pytest.approx(peak - trough)
    assert bh["max_drawdown_pct"] == pytest.approx((peak - trough) / peak)


# Pass criteria -------------------------------------------------------------------------------


def test_thresholds_come_from_config():
    def run_with(criteria):
        return Run(
            meta={
                "window": {"start": str(START), "end": str(END)},
                "broker": BROKER,
                "criteria": criteria,
            },
            trades=trades(
                [30, -20, 10], ["2025-01-01 00:00", "2025-01-01 01:00", "2025-01-01 02:00"]
            ),
            equity=equity_frame(),
        )

    loose = analyze(run_with({"min_profit_factor": 1.5, "min_trades": 3, "without_top_n": 1}))
    by_name = {c.name: c for c in loose.checks}
    assert by_name["Profit factor (net)"].passed  # 40 / 20 = 2.0
    assert by_name["Closed trades"].passed
    # by return: +30 on 1,000 = 3%, -20 on 1,030, +10 on 1,010; without the 3%:
    # 1,000 x (1 - 20/1030) x (1 + 10/1010) - 1,000 < 0
    assert by_name["Net PnL without the best trades (return method)"].passed is False
    assert not analyze(run_with({})).checks[1].passed  # default min_trades is 100
    strict = analyze(run_with({"min_profit_factor": 2.5}))
    assert not {c.name: c for c in strict.checks}["Profit factor (net)"].passed
    assert all(c.passed is None for c in strict.checks if c.threshold == "comparison")


def test_top_pct_count_rounds_up():
    assert top_pct_count(1695, 1) == 17  # 16.95
    assert top_pct_count(100, 1) == 1
    assert top_pct_count(101, 1) == 2
    assert top_pct_count(5, 1) == 1
    assert top_pct_count(0, 1) == 0
    assert top_pct_count(300, 0.5) == 2  # 1.5


def best_trades_check(pnls, criteria):
    exits = pd.date_range("2025-01-01 00:00", periods=len(pnls), freq="min", tz="UTC")
    run = Run(
        meta={
            "window": {"start": str(START), "end": str(END)},
            "broker": BROKER,
            "criteria": criteria,
        },
        trades=trades(pnls, exits),
        equity=equity_frame(),
    )
    a = analyze(run)
    return a, {c.name: c for c in a.checks}["Net PnL without the best trades (return method)"]


def test_best_trades_criterion_needs_both_checks():
    # 200 trades: one +500 winner, 30 winners of +10, 169 losers of -1. Net 631.
    pnls = [500] + [10] * 30 + [-1] * 169
    # top 5: 631 - 500 - 40 = 91 > 0. top 1% = 2 trades: 631 - 510 = 121 > 0. Both pass.
    # USD method values (reported, not the criterion).
    a, check = best_trades_check(pnls, {"without_top_n": 5, "without_top_pct": 1})
    assert a.without_top[5] == 91
    assert a.without_top_pct == (1, 2, 121)
    assert check.threshold == "> 0 without top 5 and without top 1% (2 trades)"
    a, _ = best_trades_check(pnls, {"without_top_n": 5, "without_top_pct": 10})
    assert a.without_top_pct == (10, 20, -59)
    a, _ = best_trades_check(pnls, {"without_top_n": 15, "without_top_pct": 1})
    assert a.without_top[15] == -9


# Return method ---------------------------------------------------------------------------
# Starting capital 1,000 (BROKER). Four trades in order:
#   +600 on 1,000 = +60%  -> 1,600
#   -320 on 1,600 = -20%  -> 1,280
#   +640 on 1,280 = +50%  -> 1,920
#   -288 on 1,920 = -15%  -> 1,632      net +632
COMPOUND = [600, -320, 640, -288]


def test_trade_returns_use_equity_at_entry():
    returns = trade_returns(trades(COMPOUND, EXITS[:4]), 1000)
    assert returns.tolist() == pytest.approx([0.6, -0.2, 0.5, -0.15])
    # Compounding all returns gives back the real net PnL.
    assert compounded_without_top(returns, 1000, 0) == pytest.approx(632)


def test_return_and_usd_methods_disagree():
    t = trades(COMPOUND, EXITS[:4])
    # USD: the best trade is the late +640 (larger only because equity grew): 632 - 640 = -8.
    assert pnl_without_top(t, 1) == -8
    # Return: the best trade is the early +60%: 1,000 x 0.8 x 1.5 x 0.85 = 1,020, net +20.
    returns = trade_returns(t, 1000)
    assert compounded_without_top(returns, 1000, 1) == pytest.approx(20)


def test_best_trades_criterion_uses_the_return_method():
    # top 1 and top 1% (ceil(0.04) = 1 trade): both +20 by return, -8 by USD. Passes.
    a, check = best_trades_check(COMPOUND, {"without_top_n": 1, "without_top_pct": 1})
    assert a.without_top[1] == -8 and a.without_top_pct[2] == -8
    assert a.without_top_return[1] == pytest.approx(20)
    assert a.without_top_pct_return[:2] == (1, 1)
    assert check.passed
    assert check.value == "top 1: 20.00; top 1%: 20.00"


def test_best_trades_criterion_needs_both_return_checks():
    # top 2 by return (+60%, +50%): 1,000 x 0.8 x 0.85 = 680, net -320. top 1% passes (+20).
    a, check = best_trades_check(COMPOUND, {"without_top_n": 2, "without_top_pct": 1})
    assert a.without_top_return[2] == pytest.approx(-320)
    assert check.passed is False
    # top 1 passes (+20), top 50% = 2 trades fails (-320).
    a, check = best_trades_check(COMPOUND, {"without_top_n": 1, "without_top_pct": 50})
    assert a.without_top_pct_return[1:] == (2, pytest.approx(-320))
    assert check.passed is False


def test_unknown_criterion_is_rejected():
    with pytest.raises(ValueError, match="unknown criteria"):
        Criteria.from_dict({"min_pf": 1.3})


def test_metrics_read_a_written_run_folder(tmp_path):
    """End to end through the files: engine run -> write_run -> load_run -> analyze."""
    params = {"start": "2025-01-03T00:00:00Z", "end": "2025-02-20T00:00:00Z"}
    result = Backtest(random_walk(1500, 7), EmaVwap, BrokerConfig(), params).run()
    meta = {
        "window": {"start": params["start"], "end": params["end"]},
        "broker": {
            "initial_capital": "10000",
            "commission_pct": "0.05",
            "slippage_ticks": 2,
            "tick_size": "0.01",
            "lot_size": "0.00001",
            "point_value": "1",
        },
        "criteria": {},
    }
    folder = write_run(result, tmp_path, "case", "", meta)
    a = analyze(load_run(folder))
    s = summarize(result)
    assert a.stats["trades"] == s.trades > 0
    assert a.stats["net_pnl"] == pytest.approx(float(s.net_pnl))
    assert a.stats["profit_factor"] == pytest.approx(s.profit_factor)
