"""True-peak (BS.1770-5 Annex 2) reducer + PSR derivation.

The reducer tracks per-channel maximum absolute amplitude over the 4x
oversampled stream from :class:`~asmr_balance.nodes.oversample.Oversample4xPolyphase`.
After both this reducer and :class:`~asmr_balance.metrics.lra.LRAReducer`
finalize, :func:`derive_psr_db` composes the peak-to-short-term-loudness
ratio in :class:`~asmr_balance.metrics.subtrees.DynamicsMetrics`.

We deliberately *do not* couple TruePeak and LRA inside a single reducer
(would violate the one-reducer-per-subtree discipline). Instead the assemble
step is responsible for deriving PSR from two independent subtrees.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import ClassVar

import numpy as np

from asmr_balance.graph.types import OversampledBlock
from asmr_balance.metrics.subtrees import DynamicsMetrics, LRAMetrics


def _peak_dbtp(peak_abs: float) -> float:
    """Convert linear amplitude to dBTP. ``0`` linear ⇒ ``-inf`` dBTP."""
    if peak_abs <= 0.0 or not math.isfinite(peak_abs):
        return float("-inf")
    return 20.0 * math.log10(peak_abs)


@dataclass(slots=True)
class TruePeakReducer:
    """``Stream[OversampledBlock] → (max_abs_l, max_abs_r)`` (linear)."""

    name: ClassVar[str] = "truepeak"

    _max_abs_l: float = 0.0
    _max_abs_r: float = 0.0

    def update(self, payload: OversampledBlock) -> None:
        if payload.shape[0] == 0:
            return
        left_peak = float(np.max(np.abs(payload[:, 0])))
        right_peak = float(np.max(np.abs(payload[:, 1])))
        if left_peak > self._max_abs_l:
            self._max_abs_l = left_peak
        if right_peak > self._max_abs_r:
            self._max_abs_r = right_peak

    def finalize(self) -> _TruePeakAggregate:
        """Return the *intermediate* peak aggregate; ``derive_psr_db`` finishes it."""
        return _TruePeakAggregate(max_abs_l=self._max_abs_l, max_abs_r=self._max_abs_r)


@dataclass(frozen=True, slots=True)
class _TruePeakAggregate:
    """Linear max-|x| per channel; finalized into :class:`DynamicsMetrics` by ``derive_psr_db``."""

    max_abs_l: float
    max_abs_r: float


def derive_psr_db(peak: _TruePeakAggregate, lra: LRAMetrics) -> DynamicsMetrics:
    """Compose :class:`DynamicsMetrics` from independent peak and short-term subtrees.

    PSR = ``max(dBTP_L, dBTP_R) − max_short_term_lufs``.

    When either input is undefined (silent file or empty short-term stream),
    ``psr_db`` is ``NaN``; the dBTP fields use ``-inf`` to represent silence.
    """
    dbtp_l = _peak_dbtp(peak.max_abs_l)
    dbtp_r = _peak_dbtp(peak.max_abs_r)
    dbtp_max = max(dbtp_l, dbtp_r)
    if math.isfinite(dbtp_max) and math.isfinite(lra.max_short_term_lufs):
        psr_db = dbtp_max - lra.max_short_term_lufs
    else:
        psr_db = float("nan")
    return DynamicsMetrics(
        true_peak_dbtp_l=dbtp_l,
        true_peak_dbtp_r=dbtp_r,
        true_peak_dbtp_max=dbtp_max,
        psr_db=psr_db,
    )
