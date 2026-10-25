"""Report charts as inline SVG strings. matplotlib's object API only, no pyplot state."""

import io

import matplotlib
import pandas as pd
from matplotlib.figure import Figure

matplotlib.rcParams["svg.fonttype"] = "none"  # text stays text, no embedded glyph paths
matplotlib.rcParams["svg.hashsalt"] = "real-edge-backtest"  # stable element ids

STRATEGY, BENCHMARK, NEGATIVE = "#1f5fa8", "#8a8a8a", "#b23b3b"


def _svg(fig: Figure, key: str) -> str:
    """SVG markup without the XML prolog. Element ids get a per-chart prefix, so several charts
    inline in one page cannot resolve each other's clip paths or markers."""
    buffer = io.StringIO()
    fig.savefig(buffer, format="svg", bbox_inches="tight")
    text = buffer.getvalue()
    text = text[text.index("<svg") :]
    return (
        text.replace('id="', f'id="{key}-')
        .replace("url(#", f"url(#{key}-")
        .replace('href="#', f'href="#{key}-')
    )


def _figure() -> tuple[Figure, object]:
    fig = Figure(figsize=(9, 3.2))
    ax = fig.add_subplot()
    ax.grid(True, alpha=0.3)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    return fig, ax


def equity_chart(time: pd.Series, equity: pd.Series, closed: pd.Series) -> str:
    fig, ax = _figure()
    ax.plot(time, equity, color=STRATEGY, linewidth=1, label="Equity at close")
    ax.step(
        closed.index,
        closed.values,
        where="post",
        color=BENCHMARK,
        linewidth=0.8,
        label="Closed trades",
    )
    ax.set_ylabel("USD")
    ax.legend(loc="upper left", frameon=False)
    return _svg(fig, "equity")


def drawdown_chart(time: pd.Series, equity: pd.Series, initial: float) -> str:
    peak = equity.cummax().clip(lower=initial)
    drawdown = equity / peak - 1
    fig, ax = _figure()
    ax.fill_between(time, drawdown * 100, 0, color=NEGATIVE, alpha=0.4, linewidth=0)
    ax.set_ylabel("Drawdown %")
    return _svg(fig, "drawdown")


def yearly_chart(years: list[int], strategy: list[float], benchmark: list[float]) -> str:
    fig, ax = _figure()
    x = range(len(years))
    width = 0.4
    ax.bar(
        [i - width / 2 for i in x],
        [r * 100 for r in strategy],
        width,
        color=STRATEGY,
        label="Strategy",
    )
    ax.bar(
        [i + width / 2 for i in x],
        [r * 100 for r in benchmark],
        width,
        color=BENCHMARK,
        label="Buy and hold",
    )
    ax.axhline(0, color="black", linewidth=0.6)
    ax.set_xticks(list(x), [str(y) for y in years])
    ax.set_ylabel("Return %")
    ax.legend(loc="upper left", frameon=False)
    return _svg(fig, "yearly")


def comparison_chart(time: pd.Series, strategy: pd.Series, benchmark: pd.Series) -> str:
    fig, ax = _figure()
    ax.plot(time, strategy, color=STRATEGY, linewidth=1, label="Strategy")
    ax.plot(time, benchmark, color=BENCHMARK, linewidth=1, label="Buy and hold")
    ax.set_yscale("log")
    ax.set_ylabel("USD (log)")
    ax.legend(loc="upper left", frameon=False)
    return _svg(fig, "comparison")
