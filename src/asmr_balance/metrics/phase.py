"""Low-band phase coherence reducer.

Consumes the :data:`~asmr_balance.graph.types.LowPassBlock` stream
(``< 300 Hz``) produced by the shared :class:`~asmr_balance.nodes.lowpass.LowPassFilter`
and computes a Welford Pearson L/R correlation. Values near ``+1`` indicate
phase-coherent bass; near ``-1`` indicate inverted bass (the phase-inversion
rule trigger).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

import numpy as np

from asmr_balance.graph.types import LowPassBlock
from asmr_balance.metrics.subtrees import PhaseMetrics


@dataclass(slots=True)
class LowPhaseCoherenceReducer:
    """``Stream[LowPassBlock] → PhaseMetrics`` (Welford Pearson on L/R)."""

    name: ClassVar[str] = "phase"

    _n: int = 0
    _mean_l: float = 0.0
    _mean_r: float = 0.0
    _m2_l: float = 0.0
    _m2_r: float = 0.0
    _cov: float = 0.0

    def update(self, payload: LowPassBlock) -> None:
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

        if self._n == 0:
            self._n = n_b
            self._mean_l = mean_l_b
            self._mean_r = mean_r_b
            self._m2_l = m2_l_b
            self._m2_r = m2_r_b
            self._cov = cov_b
            return

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

    def finalize(self) -> PhaseMetrics:
        nan = float("nan")
        if self._n < 2:
            return PhaseMetrics(low_phase_coherence=nan)
        denom = (self._m2_l * self._m2_r) ** 0.5
        if denom <= 0.0:
            return PhaseMetrics(low_phase_coherence=nan)
        return PhaseMetrics(low_phase_coherence=self._cov / denom)
