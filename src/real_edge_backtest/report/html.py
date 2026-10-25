"""Self-contained HTML report of one run folder. Inline CSS and SVG, no scripts, no external assets.

Trade metrics always come from analysis.metrics. QuantStats, if installed (extra "report"),
adds a separate section of period-based metrics computed from daily window returns.
"""

import html
import math
import warnings
from pathlib import Path
from typing import Any

import pandas as pd

from real_edge_backtest.analysis.metrics import Analysis, Run, analyze, load_run
from real_edge_backtest.experiments import describe_seen
from real_edge_backtest.report import charts

CSS = """
:root { color-scheme: light; }
body { font: 14px/1.45 system-ui, -apple-system, "Segoe UI", sans-serif; color: #1d1d1f;
  background: #fff; margin: 0 auto; max-width: 1040px; padding: 24px 16px 64px; }
h1 { font-size: 22px; margin: 0 0 4px; }
h2 { font-size: 17px; margin: 36px 0 10px; border-bottom: 1px solid #ddd; padding-bottom: 4px; }
p.note { color: #555; margin: 4px 0 12px; }
table { border-collapse: collapse; margin: 8px 0; font-variant-numeric: tabular-nums; }
th, td { padding: 3px 10px; border-bottom: 1px solid #eee; text-align: right; }
th:first-child, td:first-child { text-align: left; }
th { background: #f6f6f6; font-weight: 600; }
.meta td { text-align: left; }
.pass { color: #18794e; font-weight: 600; }
.fail { color: #b23b3b; font-weight: 600; }
.info { color: #555; }
.warn { background: #fff4d6; border: 1px solid #e6c46a; padding: 8px 12px; margin: 8px 0; }
.chart svg { max-width: 100%; height: auto; }
.scroll { max-height: 520px; overflow: auto; border: 1px solid #eee; }
"""


def _e(value: Any) -> str:
    return html.escape(str(value))


def _money(value: float) -> str:
    return f"{value:,.2f}"


def _pct(value: float) -> str:
    return f"{value:.2%}"


def _pf(value: float) -> str:
    return "inf" if math.isinf(value) else f"{value:.3f}"


def _table(headers: list[str], rows: list[list[Any]], cls: str = "") -> str:
    head = "".join(f"<th>{_e(h)}</th>" for h in headers)
    body = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in row) + "</tr>" for row in rows)
    attr = f' class="{cls}"' if cls else ""
    return f"<table{attr}><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


def _kv(rows: list[tuple[str, Any]]) -> str:
    body = "".join(f"<tr><td>{_e(k)}</td><td>{_e(v)}</td></tr>" for k, v in rows)
    return f'<table class="meta"><tbody>{body}</tbody></table>'


# Sections ------------------------------------------------------------------------------------


def _seen_text(seen: dict | None) -> str:
    if not seen:
        return "not recorded"
    return describe_seen(seen)


def header(run: Run) -> str:
    m = run.meta
    b, prov = m["broker"], m.get("provenance", {})
    sizing = m.get("sizing", {"mode": "percent_equity"})
    sizing_text = ", ".join(f"{k} {v}" for k, v in sizing.items() if k != "mode")
    dirty = prov.get("dirty")
    rows = [
        ("Strategy", f"{m.get('strategy')} ({m.get('name')})"),
        ("Market", f"{m.get('symbol')} {m.get('interval')}"),
        (
            "Window (UTC, candle close time, end exclusive)",
            f"{m['window']['start']} to {m['window']['end']}",
        ),
        ("Seen window", _seen_text(m.get("seen_window"))),
        ("Fill model", b.get("fill_model")),
        ("Fees", f"{b['commission_pct']}% per side"),
        ("Slippage", f"{b['slippage_ticks']} ticks of {b['tick_size']}"),
        ("Sizing", sizing["mode"] + (f" ({sizing_text})" if sizing_text else "")),
        ("Starting equity", f"{_money(run.initial_capital)} USD"),
        ("Config SHA-256", prov.get("config_sha256", "unknown")),
        ("Git commit", prov.get("commit", "unknown")),
        ("Working tree", "unknown" if dirty is None else ("dirty" if dirty else "clean")),
        ("Data SHA-256", prov.get("data_sha256", "unknown")),
    ]
    warning_html = "".join(f'<div class="warn">{_e(w)}</div>' for w in m.get("warnings", []))
    return f"<h1>Backtest report: {_e(m.get('name'))}</h1>{warning_html}{_kv(rows)}"


def pass_block(a: Analysis) -> str:
    rows = []
    for c in a.checks:
        if c.passed is None:
            verdict = '<span class="info">comparison</span>'
        else:
            verdict = (
                '<span class="pass">pass</span>' if c.passed else '<span class="fail">fail</span>'
            )
        rows.append([_e(c.name), _e(c.threshold), _e(c.value), verdict])
    overall = (
        '<span class="pass">all pass criteria met</span>'
        if a.passed
        else ('<span class="fail">at least one pass criterion failed</span>')
    )
    return f"<h2>Pass criteria</h2><p>{overall}</p>" + _table(
        ["Criterion", "Threshold", "Value", "Result"], rows
    )


def metric_rows(a: Analysis) -> list[tuple[str, str]]:
    s = a.stats
    rows = [
        ("Closed trades", str(s["trades"])),
        ("Net PnL", _money(s["net_pnl"])),
        ("Return", _pct(a.total_return)),
        ("Profit factor", _pf(s["profit_factor"])),
        ("Expectancy per trade", _money(s["expectancy"])),
        ("Win rate", _pct(s["win_rate"])),
        ("Average win", _money(s["average_win"])),
        ("Average loss", _money(s["average_loss"])),
    ]
    pct, removed, _ = a.without_top_pct
    for method, by_n, by_pct in (
        ("return method", a.without_top_return, a.without_top_pct_return),
        ("USD method (distorted by compounding)", a.without_top, a.without_top_pct),
    ):
        rows += [(f"Net PnL without top {n}, {method}", _money(v)) for n, v in by_n.items()]
        rows.append(
            (f"Net PnL without top {pct:g}% ({removed} trades), {method}", _money(by_pct[2]))
        )
    rows += [
        ("Time in market", _pct(a.time_in_market)),
        ("Max drawdown, close equity", f"{_money(a.max_drawdown[0])} ({_pct(a.max_drawdown[1])})"),
        (
            "Max drawdown, closed trades",
            f"{_money(a.closed_drawdown[0])} ({_pct(a.closed_drawdown[1])})",
        ),
    ]
    return rows


def trade_metrics(a: Analysis) -> str:
    bh = a.buy_and_hold
    bh_rows = [
        ("Return", _pct(bh["return"])),
        (
            "Max drawdown, close equity",
            f"{_money(bh['max_drawdown'])} ({_pct(bh['max_drawdown_pct'])})",
        ),
        ("Time in market", _pct(bh["time_in_market"])),
        ("Entry / exit price", f"{_money(bh['entry_price'])} / {_money(bh['exit_price'])}"),
    ]
    return (
        "<h2>Trade metrics</h2>"
        + '<p class="note">Return method: each trade\'s net return on equity at entry, the best '
        "trades removed, the rest compounded in order from the starting equity. USD method: the "
        "best trades' USD PnL subtracted; under percent of equity sizing later trades are larger "
        "in USD only because equity grew.</p>"
        + _kv(metric_rows(a))
        + '<h2>Buy and hold</h2><p class="note">One buy at the first window bar\'s open plus '
        "slippage, sold at the last window bar's close, same commission and starting equity.</p>"
        + _kv(bh_rows)
    )


def _bh_years(curve: pd.Series, initial: float) -> dict[int, float]:
    out, previous = {}, initial
    for year, values in curve.groupby(curve.index.year):
        out[int(year)] = float(values.iloc[-1]) / previous - 1
        previous = float(values.iloc[-1])
    return out


def chart_section(a: Analysis, run: Run) -> str:
    w = a.window
    capital = run.initial_capital
    closed = run.trades[run.trades["exit_time"].notna()].sort_values("exit_time")
    closed_curve = pd.Series(
        [capital, *(capital + closed["net_pnl"].cumsum())],
        index=[w["time_close"].iloc[0], *closed["exit_time"]],
    )
    bh_years = _bh_years(a.buy_and_hold["curve"], capital)
    years = list(a.years["year"])
    parts = [
        ("Equity curve", charts.equity_chart(w["time_close"], w["equity"], closed_curve)),
        ("Drawdown", charts.drawdown_chart(w["time_close"], w["equity"], capital)),
        (
            "Return per year",
            charts.yearly_chart(
                years, list(a.years["return"]), [bh_years.get(y, 0.0) for y in years]
            ),
        ),
        (
            "Strategy vs buy and hold",
            charts.comparison_chart(
                w["time_close"], w["equity"], a.buy_and_hold["curve"].reset_index(drop=True)
            ),
        ),
    ]
    return "".join(f'<h2>{_e(t)}</h2><div class="chart">{svg}</div>' for t, svg in parts)


def periods(a: Analysis) -> str:
    year_rows = [
        [
            int(r.year),
            int(r.trades),
            _money(r.net_pnl),
            _pf(r.profit_factor),
            _pct(r.win_rate),
            _pct(r["return"]),
        ]
        for _, r in a.years.iterrows()
    ]
    half_rows = [
        [
            h["half"],
            f"{h['from']:%Y-%m-%d %H:%M} to {h['to']:%Y-%m-%d %H:%M}",
            h["trades"],
            _money(h["net_pnl"]),
            _pf(h["profit_factor"]),
            _pct(h["win_rate"]),
        ]
        for h in a.halves
    ]
    return (
        "<h2>Per year (UTC, by exit)</h2>"
        + _table(["Year", "Trades", "Net PnL", "PF", "Win rate", "Equity return"], year_rows)
        + "<h2>Halves of the window (by exit)</h2>"
        + _table(["Half", "Period", "Trades", "Net PnL", "PF", "Win rate"], half_rows)
    )


def gap_section(run: Run, a: Analysis) -> str:
    gaps = run.meta.get("gaps")
    if "touches_gap" not in run.trades or gaps is None:
        return "<h2>Gap sensitivity</h2><p>No gap information in this run.</p>"
    touched = run.trades["touches_gap"].astype(bool)
    clean = analyze(run, run.trades[~touched])
    rows = [
        [_e(k), _e(v1), _e(v2)]
        for (k, v1), (_, v2) in zip(metric_rows(a), metric_rows(clean), strict=True)
        if not k.startswith(("Return", "Time in market", "Max drawdown, close"))
    ]
    return (
        "<h2>Gap sensitivity</h2>"
        f'<p class="note">{gaps["count"]} gaps in the dataset, {gaps["above_threshold"]} '
        f"with at least {gaps['min_gap_bars']} missing candles (entries blocked until the "
        f"indicators have enough contiguous candles). {gaps.get('ignored_signals', 0)} crosses "
        f"were ignored inside that block. {int(touched.sum())} trades were open across a gap. "
        "Equity-based rows are omitted because removing trades does not give a real equity "
        "curve.</p>" + _table(["Metric", "All trades", "Without gap trades"], rows)
    )


def quantstats_section(a: Analysis) -> str:
    try:
        import quantstats as qs
    except ImportError:
        return ""
    equity = a.window.set_index("time_close")["equity"]
    returns = equity.resample("1D").last().dropna().pct_change().dropna()
    returns.index = returns.index.tz_localize(None)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        table = qs.reports.metrics(returns, mode="full", display=False, periods_per_year=365)
    rows = [[_e(name), _e(value)] for name, value in table.iloc[:, 0].items() if str(name).strip()]
    return (
        "<h2>Period-based metrics (QuantStats)</h2>"
        f'<p class="note">QuantStats {_e(qs.__version__)} on daily returns of the window equity '
        "(UTC days, 365 periods per year). Not trade metrics; those are above.</p>"
        + _table(["Metric", "Value"], rows)
    )


def trade_list(run: Run) -> str:
    t = run.trades
    columns = [
        c
        for c in (
            "number",
            "side",
            "entry_time",
            "entry_price",
            "exit_time",
            "exit_price",
            "qty",
            "exit_comment",
            "net_pnl",
            "touches_gap",
            "sizing_capped",
        )
        if c in t
    ]
    rows = []
    for _, r in t.iterrows():
        cells = []
        for c in columns:
            v = r[c]
            if isinstance(v, pd.Timestamp):
                v = f"{v:%Y-%m-%d %H:%M}"
            elif c in ("entry_price", "exit_price", "net_pnl") and pd.notna(v):
                v = _money(v)
            elif pd.isna(v):
                v = ""
            cells.append(_e(v))
        rows.append(cells)
    return (
        '<h2>Trades (times are candle open, UTC)</h2><div class="scroll">'
        + _table(columns, rows)
        + "</div>"
    )


def render(run: Run) -> str:
    a = analyze(run)
    body = "".join(
        [
            header(run),
            pass_block(a),
            trade_metrics(a),
            chart_section(a, run),
            periods(a),
            gap_section(run, a),
            quantstats_section(a),
            trade_list(run),
        ]
    )
    title = _e(f"Report {run.meta.get('name')}")
    return (
        f'<!doctype html><html lang="en"><head><meta charset="utf-8">'
        f'<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>{title}</title><style>{CSS}</style></head><body>{body}</body></html>\n"
    )


def write_report(folder: Path, out: Path | None = None) -> Path:
    target = out or folder / "report.html"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(render(load_run(folder)), encoding="utf-8")
    return target
