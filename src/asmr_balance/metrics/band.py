"""Per-band L/R imbalance reducer with 4-band roll-up.

Consumes :data:`~asmr_balance.nodes.bandsplit.BandedFrame` payloads (31
1/3-octave band stereo arrays) and accumulates per-band running sums of
``L²`` and ``R²``. At finalization we compute the 31-band imbalances in dB
and the four legacy aggregates (low / low_mid / high_mid / high) as
mathematical partition sums of the same 31 bands — no extra IIR pass.

The aggregation correctness is property-tested
(:mod:`tests.property.test_band_rollup`): 31-band L/R energies summed over
the partition equal the 4-band L/R energies, modulo identical floating-point
rounding.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import ClassVar

import math
import numpy as np

from asmr_balance.nodes.bandsplit import BANDS, BandedFrame, BandSpec, FourBandPartition
from asmr_balance.metrics.subtrees import BandImbalanceMetrics


def _safe_ratio_db(l_energy: float, r_energy: float) -> float:
    """``10·log10(L / R)``; NaN when either side is non-positive."""
    if l_energy <= 0.0 or r_energy <= 0.0 or not math.isfinite(l_energy) or not math.isfinite(r_energy):
        return float("nan")
    return 10.0 * math.log10(l_energy / r_energy)


@dataclass(slots=True)
class BandImbalanceReducer:
    """``Stream[BandedFrame] → BandImbalanceMetrics``."""

    name: ClassVar[str] = "band"

    bands: tuple[BandSpec, ...] = BANDS
    partition: FourBandPartition = field(init=False)
    _sum_l_sq: dict[str, float] = field(init=False)
    _sum_r_sq: dict[str, float] = field(init=False)

    def __post_init__(self) -> None:
        self.partition = FourBandPartition.from_bands(self.bands)
        self._sum_l_sq = {b.name: 0.0 for b in self.bands}
        self._sum_r_sq = {b.name: 0.0 for b in self.bands}

    def update(self, payload: BandedFrame) -> None:
        for name, arr in payload.items():
            # Sum L² and R² for this band, this frame.
            left = arr[:, 0]
            right = arr[:, 1]
            self._sum_l_sq[name] += float(np.dot(left, left))
            self._sum_r_sq[name] += float(np.dot(right, right))

    def finalize(self) -> BandImbalanceMetrics:
        third_octave = {
            name: _safe_ratio_db(self._sum_l_sq[name], self._sum_r_sq[name])
            for name in self._sum_l_sq
        }
        aggregates = {
            "low": self.partition.low,
            "low_mid": self.partition.low_mid,
            "high_mid": self.partition.high_mid,
            "high": self.partition.high,
        }
        rolled: dict[str, float] = {}
        for slot, names in aggregates.items():
            l_sum = sum(self._sum_l_sq[n] for n in names)
            r_sum = sum(self._sum_r_sq[n] for n in names)
            rolled[slot] = _safe_ratio_db(l_sum, r_sum)
        return BandImbalanceMetrics(
            low=rolled["low"],
            low_mid=rolled["low_mid"],
            high_mid=rolled["high_mid"],
            high=rolled["high"],
            third_octave=third_octave,
        )
