"""Stereo correlation reducer — Welford Pearson L/R + mid-side energy ratio.

Both metrics are streaming-friendly:

* Pearson uses the Chan–Golub–LeVeque (CGL) parallel update for variance and
  covariance, accumulating ``(n, μ_L, μ_R, M2_L, M2_R, C)``. The CGL form is
  numerically stable for long streams and proven associative under chunk
  merge — handy if we ever lift to monoid-based parallel reducers.
* Mid-side energy ratio (``M = (L + R) / 2``, ``S = (L − R) / 2``) reduces to
  running sums ``Σ M²`` and ``Σ S²``.

Both quantities are derived from the raw :data:`~asmr_balance.graph.types.RawBlock`
stream (no K-weighting), so the reducer is wired downstream of the source
node directly.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

import numpy as np

from asmr_balance.graph.types import RawBlock
from asmr_balance.metrics.subtrees import StereoCorrelationMetrics


@dataclass(slots=True)
class StereoCorrelationReducer:
    """``Stream[RawBlock] → StereoCorrelationMetrics``."""

    name: ClassVar[str] = "correlation"

    # Welford state
    _n: int = 0
    _mean_l: float = 0.0
    _mean_r: float = 0.0
    _m2_l: float = 0.0
    _m2_r: float = 0.0
    _cov: float = 0.0
    # Mid-side energy
    _sum_m_sq: float = 0.0
    _sum_s_sq: float = 0.0

    def update(self, payload: RawBlock) -> None:
        if payload.shape[0] == 0:
            return
        left = np.asarray(payload[:, 0], dtype=np.float64)
        right = np.asarray(payload[:, 1], dtype=np.float64)
        n_b = left.size
        mean_l_b = float(np.mean(left))
        mean_r_b = float(np.mean(right))
        dl = left - mean_l_b
        dr = right - mean_r_b
        m2_l_b = float(np.sum(dl * dl))
        m2_r_b = float(np.sum(dr * dr))
        cov_b = float(np.sum(dl * dr))

        # CGL parallel merge of (n, μ, M2) and the cross moment C.
        if self._n == 0:
            self._n = n_b
            self._mean_l = mean_l_b
            self._mean_r = mean_r_b
            self._m2_l = m2_l_b
            self._m2_r = m2_r_b
            self._cov = cov_b
        else:
            n_a = self._n
            n_t = n_a + n_b
            delta_l = mean_l_b - self._mean_l
            delta_r = mean_r_b - self._mean_r
            self._m2_l = self._m2_l + m2_l_b + delta_l * delta_l * (n_a * n_b / n_t)
            self._m2_r = self._m2_r + m2_r_b + delta_r * delta_r * (n_a * n_b / n_t)
            self._cov = self._cov + cov_b + delta_l * delta_r * (n_a * n_b / n_t)
            self._mean_l = self._mean_l + delta_l * (n_b / n_t)
            self._mean_r = self._mean_r + delta_r * (n_b / n_t)
            self._n = n_t

        # Mid-side energy is additive.
        mid = 0.5 * (left + right)
        side = 0.5 * (left - right)
        self._sum_m_sq += float(np.sum(mid * mid))
        self._sum_s_sq += float(np.sum(side * side))

    def finalize(self) -> StereoCorrelationMetrics:
        nan = float("nan")
        if self._n < 2:
            return StereoCorrelationMetrics(pearson_r=nan, ms_ratio_db=nan)
        denom = (self._m2_l * self._m2_r) ** 0.5
        if denom <= 0.0:
            pearson_r = nan
        else:
            pearson_r = self._cov / denom
        if self._sum_s_sq <= 0.0 and self._sum_m_sq <= 0.0:
            ms_ratio_db = nan
        elif self._sum_s_sq <= 0.0:
            ms_ratio_db = float("inf")
        elif self._sum_m_sq <= 0.0:
            ms_ratio_db = float("-inf")
        else:
            ms_ratio_db = 10.0 * float(np.log10(self._sum_m_sq / self._sum_s_sq))
        return StereoCorrelationMetrics(pearson_r=pearson_r, ms_ratio_db=ms_ratio_db)
