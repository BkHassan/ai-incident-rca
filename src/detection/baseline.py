"""Causal baselines: statistics of past observations only.

For observation ``t`` there are two baselines, both computed from values seen before ``t``:

* ``recent()``: the last ``window`` accepted observations. This is a shifted rolling window,
  which responds to spikes and steps.
* ``lagged(lag)``: ``window`` accepted observations ending ``lag`` observations earlier. It
  responds to gradual drift, which a recent window follows too closely to flag.

The current value is never part of its own baseline, and later values cannot affect it.
``CausalBaseline`` enforces this by design: the baselines are read before the new value is
passed to ``add()``.
"""

from __future__ import annotations

import math
from collections import deque
from collections.abc import Iterable, Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class BaselineStats:
    mean: float
    std: float  # sample standard deviation (ddof=1)
    count: int


def _stats(values: Sequence[float]) -> BaselineStats:
    n = len(values)
    mean = math.fsum(values) / n
    variance = math.fsum((v - mean) ** 2 for v in values) / (n - 1)
    return BaselineStats(mean=mean, std=math.sqrt(variance), count=n)


class CausalBaseline:
    """History of past observations that were accepted into the baseline."""

    def __init__(self, window: int, min_points: int, max_lag: int = 0):
        if not 2 <= min_points <= window:
            raise ValueError("need 2 <= min_points <= window")
        if max_lag < 0:
            raise ValueError("max_lag must be >= 0")
        self.window = window
        self.min_points = min_points
        self._values: deque[float] = deque(maxlen=window + max_lag)

    def recent(self) -> BaselineStats | None:
        """Statistics of the last ``window`` accepted observations, or ``None`` during warm-up."""
        return self.lagged(0)

    def lagged(self, lag: int) -> BaselineStats | None:
        """Statistics of ``window`` accepted observations that end ``lag`` observations before now."""
        if lag > self._values.maxlen - self.window:
            raise ValueError(f"lag {lag} exceeds the history kept (max_lag {self._values.maxlen - self.window})")
        end = len(self._values) - lag
        values = list(self._values)[max(0, end - self.window):max(0, end)]
        return _stats(values) if len(values) >= self.min_points else None

    def add(self, value: float) -> None:
        """Accept an observation into the baseline for later observations."""
        self._values.append(value)


def causal_rolling_baseline(values: Iterable[float], window: int, min_points: int) -> list[BaselineStats | None]:
    """Baseline of every observation from the ``window`` values before it, without excluding any.

    Equivalent to pandas ``series.shift(1).rolling(window, min_periods=min_points)``.
    """
    baseline = CausalBaseline(window, min_points)
    out = []
    for value in values:
        out.append(baseline.recent())
        baseline.add(value)
    return out
