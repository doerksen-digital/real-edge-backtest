"""Indicators against hand calculations of the Pine v6 reference definitions."""

import numpy as np
import pytest

from real_edge_backtest.indicators import (
    atr,
    crossover,
    crossunder,
    ema,
    pine_round,
    rma,
    rolling_sum,
    rolling_vwap,
    sma,
    true_range,
)

nan = np.nan


def arr(*values: float) -> np.ndarray:
    return np.array(values, dtype=float)


def test_ema_seeds_with_first_value():
    # alpha = 2 / 3: 1, 2/3*2 + 1/3*1 = 5/3, 2/3*3 + 1/3*5/3 = 23/9
    np.testing.assert_allclose(ema(arr(1, 2, 3), 2), [1, 5 / 3, 23 / 9])


def test_ema_skips_na_and_carries_value():
    np.testing.assert_allclose(ema(arr(nan, 1, nan, 4), 2), [nan, 1, 1, 3])


def test_sma_needs_full_window():
    np.testing.assert_allclose(sma(arr(1, 2, 3, 4), 3), [nan, nan, 2, 3])


def test_rma_seeds_with_sma_then_recurses():
    # seed sma(1, 2) = 1.5, then alpha 1/2: 0.5*3 + 0.5*1.5 = 2.25, 0.5*4 + 0.5*2.25 = 3.125
    np.testing.assert_allclose(rma(arr(1, 2, 3, 4), 2), [nan, 1.5, 2.25, 3.125])


def test_true_range_first_bar_is_high_minus_low():
    high, low, close = arr(10, 12, 11), arr(8, 11, 7), arr(9, 11.5, 8)
    # bar 1: max(1, |12-9|, |11-9|) = 3; bar 2: max(4, |11-11.5|, |7-11.5|) = 4.5
    np.testing.assert_allclose(true_range(high, low, close), [2, 3, 4.5])


def test_atr_is_rma_of_true_range():
    high, low, close = arr(10, 12, 11), arr(8, 11, 7), arr(9, 11.5, 8)
    # tr = 2, 3, 4.5; rma length 2: seed 2.5, then 0.5*4.5 + 0.5*2.5 = 3.5
    np.testing.assert_allclose(atr(high, low, close, 2), [nan, 2.5, 3.5])


def test_rolling_sum_window():
    np.testing.assert_allclose(rolling_sum(arr(1, 2, 3, 4), 3), [nan, nan, 6, 9])
    assert np.isnan(rolling_sum(arr(1, 2), 3)).all()


def test_rolling_vwap_and_zero_volume():
    high, low, close = arr(3, 6, 9), arr(3, 6, 9), arr(3, 6, 9)
    volume = arr(1, 3, 0)
    # hlc3 = 3, 6, 9. bar 1: (3*1 + 6*3) / 4 = 5.25; bar 2: (6*3 + 9*0) / 3 = 6
    np.testing.assert_allclose(rolling_vwap(high, low, close, volume, 2), [nan, 5.25, 6])
    zero = rolling_vwap(high, low, close, arr(0, 0, 0), 2)
    assert np.isnan(zero).all()


def test_crossover_counts_touch_on_previous_bar():
    a, b = arr(1, 2, 2, 3), arr(2, 2, 1, 1)
    # bar 2: 2 > 1 and previous 2 <= 2, a touch counts; bar 3: previous 2 > 1, no cross
    assert crossover(a, b).tolist() == [False, False, True, False]


def test_crossunder_mirrors_crossover():
    a, b = arr(3, 2, 2, 1), arr(2, 2, 3, 3)
    assert crossunder(a, b).tolist() == [False, False, True, False]


def test_cross_with_na_is_false():
    assert crossover(arr(nan, 2), arr(1, 1)).tolist() == [False, False]


@pytest.mark.parametrize(
    ("value", "expected"),
    [(2.5, 3), (-2.5, -2), (0.4999999, 0), (1.5, 2), (2.4999, 2)],
)
def test_pine_round_ties_round_up(value, expected):
    assert pine_round(value) == expected
    assert isinstance(pine_round(value), int)
