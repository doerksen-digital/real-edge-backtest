"""Optional entry filters and extra exit rules, configured per run as small named plug-ins.

    [[strategy.filters]]
    name = "some_filter"
    some_param = 3

    [[strategy.exits]]
    name = "some_exit"

Without plug-ins a strategy behaves exactly as before. A plug-in has default parameters in
`params`; unknown names and unknown parameters are rejected. Concrete plug-ins are added only
with the hypothesis that defines them (docs/research/hypotheses.md).

Entry filters act where the trend filter acts. For a cross that the trend filter and the
direction setting allow, each filter's on_signal answers:
- ALLOW: the next filter decides; if all allow, the entry happens at this close
- CANCEL: no entry; the cross still closes an opposite position, like a blocked cross
- defer(n): the entry waits up to n bars (at most the filter's max_defer). The opposite
  position is closed at once, like a blocked cross. At each later close the filter's
  on_pending answers ALLOW (enter at that close, sized and stopped at that bar, after the
  filters behind it allow too), CANCEL, or None (keep waiting). After n bars without ALLOW
  the signal is cancelled. A cross in the opposite direction cancels it and is then handled
  like any cross.

Exit rules run on every bar close with an open trade inside the window, before the cross
logic. They may close the trade at the close (broker.close) or tighten its stop
(broker.move_stop), which takes effect from the next bar.
"""

from dataclasses import dataclass
from typing import Any, ClassVar

ALLOW, CANCEL = "allow", "cancel"


@dataclass(frozen=True)
class Defer:
    bars: int


def defer(bars: int) -> Defer:
    return Defer(bars)


class Plugin:
    name: ClassVar[str] = ""
    params: ClassVar[dict[str, Any]] = {}

    def __init__(self, **params: Any) -> None:
        unknown = set(params) - set(self.params)
        if unknown:
            raise ValueError(f"unknown parameters for plug-in {self.name!r}: {sorted(unknown)}")
        self.p = {**self.params, **params}

    def init(self, strategy: Any) -> None:
        """Precompute arrays after the strategy's init. May only build causal values."""


class EntryFilter(Plugin):
    max_defer: ClassVar[int] = 0  # most bars a signal may wait for on_pending

    def on_signal(self, strategy: Any, i: int, side: int) -> str | Defer:
        return ALLOW

    def on_pending(self, strategy: Any, i: int, side: int, bars_waited: int) -> str | None:
        return CANCEL


class ExitRule(Plugin):
    def on_bar(self, strategy: Any, i: int, trade: Any) -> None:
        """Called at the close of bar i while `trade` is open."""


FILTERS: dict[str, type[EntryFilter]] = {}
EXITS: dict[str, type[ExitRule]] = {}


def _build(configs: list[dict[str, Any]], registry: dict[str, type], kind: str) -> list:
    plugins = []
    for config in configs:
        config = dict(config)
        name = config.pop("name", None)
        if name not in registry:
            raise ValueError(f"unknown {kind} plug-in {name!r}, known: {sorted(registry)}")
        plugins.append(registry[name](**config))
    return plugins


def build_filters(configs: list[dict[str, Any]]) -> list[EntryFilter]:
    return _build(configs, FILTERS, "entry filter")


def build_exits(configs: list[dict[str, Any]]) -> list[ExitRule]:
    return _build(configs, EXITS, "exit")
