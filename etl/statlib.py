"""Small, dependency-light statistics helpers used across the metric layer.

Kept deliberately explicit (no hidden pandas) so the math behind every label is
easy to read and audit.
"""
from __future__ import annotations

import math
from collections.abc import Sequence


def mean(xs: Sequence[float]) -> float:
    xs = list(xs)
    return sum(xs) / len(xs) if xs else 0.0


def stdev(xs: Sequence[float], *, sample: bool = True) -> float:
    xs = list(xs)
    n = len(xs)
    if n < 2:
        return 0.0
    m = mean(xs)
    var = sum((x - m) ** 2 for x in xs) / (n - 1 if sample else n)
    return math.sqrt(var)


def cv(xs: Sequence[float]) -> float:
    """Coefficient of variation = stdev / mean (lower = more consistent)."""
    m = mean(xs)
    return (stdev(xs) / m) if m else 0.0


def percentile(xs: Sequence[float], q: float) -> float:
    """Linear-interpolated percentile, q in [0,1]."""
    xs = sorted(xs)
    if not xs:
        return 0.0
    if len(xs) == 1:
        return xs[0]
    idx = q * (len(xs) - 1)
    lo = math.floor(idx)
    hi = math.ceil(idx)
    if lo == hi:
        return xs[lo]
    return xs[lo] + (xs[hi] - xs[lo]) * (idx - lo)


def percentile_rank(xs: Sequence[float], x: float) -> float:
    """Fraction of values <= x (0..1). Ties count as half."""
    xs = list(xs)
    if not xs:
        return 0.5
    below = sum(1 for v in xs if v < x)
    equal = sum(1 for v in xs if v == x)
    return (below + 0.5 * equal) / len(xs)


def zscore(xs: Sequence[float], x: float) -> float:
    s = stdev(xs)
    return (x - mean(xs)) / s if s else 0.0


def gini(xs: Sequence[float]) -> float:
    """Gini coefficient of a non-negative distribution (0 even .. 1 concentrated)."""
    xs = sorted(v for v in xs if v is not None)
    n = len(xs)
    if n == 0 or sum(xs) == 0:
        return 0.0
    cum = 0.0
    for i, x in enumerate(xs, start=1):
        cum += i * x
    return (2 * cum) / (n * sum(xs)) - (n + 1) / n


def ols_slope(ys: Sequence[float]) -> float:
    """Slope of y vs its index (trend per step)."""
    ys = list(ys)
    n = len(ys)
    if n < 2:
        return 0.0
    xs = list(range(n))
    mx, my = mean(xs), mean(ys)
    denom = sum((x - mx) ** 2 for x in xs)
    if denom == 0:
        return 0.0
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / denom


def skewness(xs: Sequence[float]) -> float:
    xs = list(xs)
    n = len(xs)
    s = stdev(xs)
    if n < 3 or s == 0:
        return 0.0
    m = mean(xs)
    return (sum((x - m) ** 3 for x in xs) / n) / (s ** 3)


def clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def safe_div(a: float, b: float, default: float = 0.0) -> float:
    return a / b if b else default
