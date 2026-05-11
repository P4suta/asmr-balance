"""Online (streaming) statistics: Welford-style Pearson correlation + M/S RMS.

Both accumulators ingest 1-D arrays via ``update`` and produce a final scalar
via ``correlation`` / ``ms_ratio_db``.  The Welford parallel-update form
(Chan–Golub–LeVeque) is numerically stable for arbitrary chunk sizes (ADR-0001).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Final

import numpy as np

if TYPE_CHECKING:
    from numpy.typing import NDArray

_INV_SQRT2: Final[float] = 1.0 / math.sqrt(2.0)


@dataclass(slots=True)
class WelfordCorrelation:
    """Two-stream online mean/variance/covariance (Pearson)."""

    n: int = 0
    mean_x: float = 0.0
    mean_y: float = 0.0
    m2_x: float = 0.0
    m2_y: float = 0.0
    cov: float = 0.0

    def update(self, x: NDArray[np.floating], y: NDArray[np.floating]) -> None:
        if x.shape != y.shape:
            msg = f"shape mismatch: {x.shape} vs {y.shape}"
            raise ValueError(msg)
        if x.size == 0:
            return
        x64 = x.astype(np.float64, copy=False)
        y64 = y.astype(np.float64, copy=False)
        n_b = x64.size
        mean_x_b = float(np.mean(x64))
        mean_y_b = float(np.mean(y64))
        dx = x64 - mean_x_b
        dy = y64 - mean_y_b
        m2_x_b = float(np.dot(dx, dx))
        m2_y_b = float(np.dot(dy, dy))
        cov_b = float(np.dot(dx, dy))

        if self.n == 0:
            self.n = n_b
            self.mean_x = mean_x_b
            self.mean_y = mean_y_b
            self.m2_x = m2_x_b
            self.m2_y = m2_y_b
            self.cov = cov_b
            return

        n_a = self.n
        n_total = n_a + n_b
        delta_x = mean_x_b - self.mean_x
        delta_y = mean_y_b - self.mean_y
        joint = (n_a * n_b) / n_total

        self.m2_x += m2_x_b + delta_x * delta_x * joint
        self.m2_y += m2_y_b + delta_y * delta_y * joint
        self.cov += cov_b + delta_x * delta_y * joint
        self.mean_x += delta_x * n_b / n_total
        self.mean_y += delta_y * n_b / n_total
        self.n = n_total

    @property
    def correlation(self) -> float:
        """Pearson ``r``; ``nan`` when undefined (n<2 or zero variance)."""
        if self.n < 2 or self.m2_x <= 0.0 or self.m2_y <= 0.0:
            return float("nan")
        return self.cov / math.sqrt(self.m2_x * self.m2_y)


@dataclass(slots=True)
class MidSideRMS:
    """Online Mid/Side energy accumulator.  ``ms_ratio_db = 10·log10(E_M / E_S)``."""

    n: int = 0
    sum_m_sq: float = 0.0
    sum_s_sq: float = 0.0

    def update(self, left: NDArray[np.floating], right: NDArray[np.floating]) -> None:
        if left.shape != right.shape:
            msg = f"shape mismatch: {left.shape} vs {right.shape}"
            raise ValueError(msg)
        if left.size == 0:
            return
        left64 = left.astype(np.float64, copy=False)
        right64 = right.astype(np.float64, copy=False)
        m = (left64 + right64) * _INV_SQRT2
        s = (left64 - right64) * _INV_SQRT2
        self.sum_m_sq += float(np.dot(m, m))
        self.sum_s_sq += float(np.dot(s, s))
        self.n += left64.size

    @property
    def ms_ratio_db(self) -> float:
        """``10·log10(E_M / E_S)``; ``+inf`` when side energy is exactly 0."""
        if self.n == 0 or self.sum_m_sq <= 0.0:
            return float("nan")
        if self.sum_s_sq <= 0.0:
            return float("inf")
        return 10.0 * math.log10(self.sum_m_sq / self.sum_s_sq)


@dataclass(slots=True)
class StereoStats:
    """Convenience composite: Pearson r + Mid/Side ratio from the same stream."""

    correlation: WelfordCorrelation = field(default_factory=WelfordCorrelation)
    mid_side: MidSideRMS = field(default_factory=MidSideRMS)

    def update(self, left: NDArray[np.floating], right: NDArray[np.floating]) -> None:
        self.correlation.update(left, right)
        self.mid_side.update(left, right)
