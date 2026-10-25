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
    by_year_side,
    closed_trade_equity,
    compounded_without_top,
    cost_stats,
    halves,
    load_run,
    max_drawdown,
    pnl_without_top,
    rolling_12m,
    slippage_cost,
    tail_trades,
    time_in_market,
    top_pct_count,
    trade_moves,
    trade_returns,
    trade_stats,
    window_equity,
    year_costs,
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
            # Cost columns default to a fee-free long; the cost tests set their own.
            "side": "long",
            "gross_pnl": [float(p) for p in pnls],
            "commission": 0.0,
            "qty": 1.0,
            "entry_price": 100.0,
            "exit_price": 100.0,
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


# Costs, sides, tails and rolling windows ----------------------------------------------------
# Slippage 2 ticks of 0.01, point value 1: each trade pays 2 fills x 0.02 x qty.
COST_BROKER = {**BROKER, "slippage_ticks": 2}


def cost_trades() -> pd.DataFrame:
    t = trades([90, -60, 20], ["2024-03-01", "2024-09-01", "2025-02-01"])
    t["side"] = ["long", "short", "long"]
    t["gross_pnl"] = [100.0, -50.0, 30.0]
    t["commission"] = [10.0, 10.0, 10.0]
    t["qty"] = [10.0, 10.0, 10.0]
    return t


def test_cost_stats():
    t = cost_trades()
    assert list(slippage_cost(t, COST_BROKER)) == pytest.approx([0.4, 0.4, 0.4])
    c = cost_stats(t, COST_BROKER)
    assert c["profit_factor_before_fees"] == pytest.approx(130 / 50)
    # before slippage too: 100.4, -49.6, 30.4
    assert c["profit_factor_before_costs"] == pytest.approx(130.8 / 49.6)
    assert c["fees"] == 30 and c["slippage"] == pytest.approx(1.2)
    assert c["gross_pnl"] == 80


def test_trade_moves_undo_slippage():
    t = cost_trades().iloc[:2].copy()
    # long: filled 100.02 -> 110.98, unslipped 100 -> 111: +11%
    # short: filled 199.98 -> 180.02, unslipped 200 -> 180: +10% for the short
    t["entry_price"] = [100.02, 199.98]
    t["exit_price"] = [110.98, 180.02]
    t["qty"] = [1.0, 2.0]
    t["commission"] = [0.2, 0.8]
    m = trade_moves(t, COST_BROKER)
    assert list(m["move_pct"]) == pytest.approx([0.11, 0.10])
    assert list(m["notional"]) == pytest.approx([100.02, 399.96])
    assert list(m["fee_pct"]) == pytest.approx([0.2 / 100.02, 0.8 / 399.96])
    assert list(m["slippage_pct"]) == pytest.approx([0.04 / 100.02, 0.08 / 399.96])


def test_year_costs_with_atr():
    t = cost_trades()
    window = pd.DataFrame(
        {
            "open_time": pd.to_datetime(["2024-06-01", "2024-07-01", "2025-01-01"], utc=True),
            "close": [100.0, 200.0, 100.0],
            "atr": [1.0, 4.0, 3.0],
        }
    )
    y = year_costs(t, window, COST_BROKER).set_index("year")
    assert y.loc[2024, "atr_pct"] == pytest.approx(0.015)  # mean of 1% and 2%
    assert y.loc[2025, "atr_pct"] == pytest.approx(0.03)
    assert y.loc[2024, "trades"] == 2 and y.loc[2024, "fees"] == 20
    assert y.loc[2025, "slippage"] == pytest.approx(0.4)
    # without an atr column (old run folders) the column is empty
    assert year_costs(t, window.drop(columns="atr"), COST_BROKER)["atr_pct"].isna().all()


def test_by_year_side():
    y = by_year_side(cost_trades())
    rows = {(r.year, r.side): r for r in y.itertuples()}
    assert rows[(2024, "long")].net_pnl == 90 and rows[(2024, "short")].net_pnl == -60
    assert rows[(2025, "long")].trades == 1 and rows[(2025, "short")].trades == 0


def test_tail_trades_rank_by_percent_return():
    # returns +60%, -20%, +50%, -15% (see COMPOUND); 50% of 4 trades = 2
    best, worst = tail_trades(trades(COMPOUND, EXITS[:4]), 1000, 50)
    assert list(best["number"]) == [1, 3]
    assert list(worst["number"]) == [2, 4]
    assert list(best["return"]) == pytest.approx([0.6, 0.5])
    best, _ = tail_trades(trades(COMPOUND, EXITS[:4]), 1000, 1)
    assert list(best["number"]) == [1]  # ceil(0.04) = 1


def test_rolling_12m():
    close = pd.date_range("2024-01-01", "2025-03-01", freq="D", tz="UTC")
    window = pd.DataFrame({"time_close": close, "equity": [1000.0 + i for i in range(len(close))]})
    t = trades([50, -25, 40, -10], ["2024-02-01", "2024-12-31", "2025-01-15", "2025-02-15"])
    r = rolling_12m(t, window)
    assert list(r["time"].dt.strftime("%Y-%m-%d")) == ["2025-01-01", "2025-02-01", "2025-03-01"]
    first = r.iloc[0]  # trades exiting 2024-01-01 to 2024-12-31: +50, -25
    assert first["trades"] == 2 and first["profit_factor"] == pytest.approx(2.0)
    assert first["return"] == pytest.approx((1000 + 366) / 1000 - 1)  # 2024 has 366 days
    last = r.iloc[2]  # 2024-03-01 to 2025-02-28: -25, +40, -10
    assert last["trades"] == 3 and last["profit_factor"] == pytest.approx(40 / 35)
