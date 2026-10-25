"""Holdout data under the research protocol (docs/PLAN.md, "Research protocol").

ETHUSDT is the validation set and SOLUSDT the final test. A strategy may run on them only with
an explicit opt-in (--holdout); such a run is marked as a holdout run in run.json, the
experiment log and the report. Downloading and checking their data needs no opt-in.
"""

HOLDOUT_SYMBOLS = ("ETHUSDT", "SOLUSDT")


class HoldoutError(ValueError):
    """A strategy run on holdout data without the explicit opt-in."""


def is_holdout(symbol: str) -> bool:
    return symbol.upper() in HOLDOUT_SYMBOLS


def check_holdout(symbol: str, allowed: bool) -> bool:
    """True if this is a holdout run. Raises HoldoutError if it is one and not allowed."""
    if is_holdout(symbol) and not allowed:
        raise HoldoutError(
            f"{symbol.upper()} is holdout data under the research protocol in docs/PLAN.md. "
            "Strategies are not run on it during development. Pass --holdout to run on it "
            "deliberately; the run is then marked as a holdout run in the log and the report."
        )
    return is_holdout(symbol)
