"""Sliding-window ΔLU summary reducer.

Consumes the same :data:`~asmr_balance.graph.types.ZBlock` stream as
:class:`~asmr_balance.metrics.loudness.IntegratedLoudnessReducer` (the graph
broadcasts a single z-block series to both nodes — no duplicate K-weighting).
For every block it derives ``ΔLU = L_block − R_block`` and at finalization
reports the empirical max, p95, std, and the time index of the maximum.

Blocks where either channel is silent (``z ≤ 0``) are dropped before the
statistic so that ``-inf − -inf = NaN`` does not pollute the percentiles.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import ClassVar, Final

import numpy as np

from asmr_balance.graph.types import ZBlock
from asmr_balance.metrics.subtrees import SlidingMetrics

_HOP_SEC: Final[float] = 0.1
_LUFS_OFFSET: Final[float] = -0.691


def _block_lufs(z: float) -> float:
    if z <= 0.0 or not math.isfinite(z):
        return float("-inf")
    return _LUFS_OFFSET + 10.0 * math.log10(z)


@dataclass(slots=True)
class SlidingImbalanceReducer:
    """``Stream[ZBlock] → SlidingMetrics``."""

    name: ClassVar[str] = "sliding"

    _z_l: list[float] = field(default_factory=list)
    _z_r: list[float] = field(default_factory=list)

    def update(self, payload: ZBlock) -> None:
        z_l, z_r = payload
        self._z_l.append(z_l)
        self._z_r.append(z_r)

    def finalize(self) -> SlidingMetrics:
        nan = float("nan")
        if not self._z_l:
            return SlidingMetrics(max_lu=nan, p95_lu=nan, std_lu=nan, t_max_sec=nan)
        l_levels = np.fromiter(
            (_block_lufs(z) for z in self._z_l), dtype=np.float64, count=len(self._z_l)
        )
        r_levels = np.fromiter(
            (_block_lufs(z) for z in self._z_r), dtype=np.float64, count=len(self._z_r)
        )
        valid = np.isfinite(l_levels) & np.isfinite(r_levels)
        if not bool(np.any(valid)):
            return SlidingMetrics(max_lu=nan, p95_lu=nan, std_lu=nan, t_max_sec=nan)
        delta = l_levels[valid] - r_levels[valid]
        abs_delta = np.abs(delta)
        max_idx = int(np.argmax(abs_delta))
        valid_positions = np.flatnonzero(valid)
        block_index = int(valid_positions[max_idx])
        return SlidingMetrics(
            max_lu=float(abs_delta.max()),
            p95_lu=float(np.percentile(abs_delta, 95)),
            std_lu=float(np.std(delta)),
            t_max_sec=block_index * _HOP_SEC,
        )
