"""Wilson score interval (scoring.wilson). A naive normal interval goes negative
at low rates; the spec forbids that."""
from __future__ import annotations

import math

import pytest

# Reference values computed from the closed-form Wilson score interval, z=1.96
# (match e.g. statsmodels.stats.proportion.proportion_confint(method="wilson")).
REFERENCE = [
    (5, 10, 0.5, 0.236590, 0.763410),
    (1, 10, 0.1, 0.017876, 0.404156),
    (3, 20, 0.15, 0.052368, 0.360423),
    (0, 10, 0.0, 0.0, 0.277540),
    (10, 10, 1.0, 0.722460, 1.0),
]


@pytest.mark.parametrize("k,n,rate,lo,hi", REFERENCE)
def test_wilson_reference_values(scoring, k, n, rate, lo, hi):
    r, l, h = scoring.wilson(k, n)
    assert r == pytest.approx(rate, abs=1e-9)
    assert l == pytest.approx(lo, abs=1e-5)
    assert h == pytest.approx(hi, abs=1e-5)


@pytest.mark.parametrize("n", [1, 2, 5, 10, 18, 30, 96, 1000])
def test_wilson_bounds_in_unit_interval_at_extremes(scoring, n):
    for k in (0, n):
        r, lo, hi = scoring.wilson(k, n)
        # Exact comparison on purpose: the naive formula gives -2.8e-17 at k=0.
        assert 0.0 <= lo <= r <= hi <= 1.0, (k, n, lo, r, hi)
    r0, lo0, hi0 = scoring.wilson(0, n)
    assert lo0 == pytest.approx(0.0, abs=1e-12) and hi0 > 0.0
    r1, lo1, hi1 = scoring.wilson(n, n)
    assert hi1 == pytest.approx(1.0, abs=1e-12) and lo1 < 1.0


@pytest.mark.parametrize("k,n", [(k, 17) for k in range(18)])
def test_wilson_contains_point_estimate(scoring, k, n):
    r, lo, hi = scoring.wilson(k, n)
    assert 0.0 <= lo <= r <= hi <= 1.0


def test_wilson_wider_z_is_wider(scoring):
    _, lo1, hi1 = scoring.wilson(3, 10, z=1.0)
    _, lo2, hi2 = scoring.wilson(3, 10, z=2.576)
    assert lo2 < lo1 and hi2 > hi1


def test_wilson_empty_cell_does_not_crash(scoring):
    # Edge case 15 (quota exhausted mid-grid) can leave a cell with n=0.
    try:
        r, lo, hi = scoring.wilson(0, 0)
    except ZeroDivisionError:
        pytest.fail("wilson(0, 0) raised ZeroDivisionError; return NaNs or (0.0, 0.0, 1.0) instead")
    except ValueError:
        return  # an explicit, documented ValueError is acceptable
    for v in (r, lo, hi):
        assert v is None or math.isnan(v) or 0.0 <= v <= 1.0
