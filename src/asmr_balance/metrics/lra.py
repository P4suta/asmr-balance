"""EBU R128 loudness range (LRA) reducer.

LRA is the difference between the 95th and 10th percentile of the gated
short-term loudness distribution (EBU R128 §3.5 / EBU Tech 3342). It uses a
relaxed two-stage gate:

* Absolute gate: ``-70 LUFS`` (same as integrated)
* Relative gate: ``-20 LU`` from the absolute-gated mean (vs. ``-10 LU`` for
  integrated loudness — this is the spec-defined difference)

Short-term loudness is computed from :data:`ShortTermZBlock` payloads
(3 s window, 100 ms hop). We also emit the max gated short-term loudness so
:func:`~asmr_balance.metrics.dynamics.derive_psr_db` can compute the
peak-to-short-term-loudness ratio.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import ClassVar, Final

import numpy as np

from asmr_balance.graph.types import ShortTermZBlock
from asmr_balance.metrics.subtrees import LRAMetrics

_LUFS_OFFSET: Final[float] = -0.691
_LRA_ABS_GATE_LUFS: Final[float] = -70.0
_LRA_REL_GATE_DROP_LU: Final[float] = 20.0


def _short_term_lufs(z_l: float, z_r: float) -> float:
    z = z_l + z_r
    if z <= 0.0 or not math.isfinite(z):
        return float("-inf")
    return _LUFS_OFFSET + 10.0 * math.log10(z)


@dataclass(slots=True)
class LRAReducer:
    """``Stream[ShortTermZBlock] → LRAMetrics``."""

    name: ClassVar[str] = "lra"

    _short_term_lufs: list[float] = field(default_factory=list)

    def update(self, payload: ShortTermZBlock) -> None:
        z_l, z_r = payload
        self._short_term_lufs.append(_short_term_lufs(z_l, z_r))

    def finalize(self) -> LRAMetrics:
        nan = float("nan")
        if not self._short_term_lufs:
            return LRAMetrics(lra_lu=nan, max_short_term_lufs=nan)
        levels = np.asarray(self._short_term_lufs, dtype=np.float64)
        finite_mask = np.isfinite(levels)
        if not bool(np.any(finite_mask)):
            return LRAMetrics(lra_lu=nan, max_short_term_lufs=nan)

        # Absolute gate.
        abs_mask = finite_mask & (levels >= _LRA_ABS_GATE_LUFS)
        if not bool(np.any(abs_mask)):
            return LRAMetrics(lra_lu=nan, max_short_term_lufs=float(np.max(levels[finite_mask])))

        ref_mean = float(np.mean(levels[abs_mask]))
        rel_threshold = ref_mean - _LRA_REL_GATE_DROP_LU
        gated_mask = abs_mask & (levels >= rel_threshold)
        if not bool(np.any(gated_mask)):  # pragma: no cover
            # Mathematically unreachable: any element of ``abs_mask`` satisfying
            # ``e >= mean(abs_kept) - 20`` will keep at least the maximum element.
            # Defensive against future relaxations of the gating thresholds.
            return LRAMetrics(lra_lu=nan, max_short_term_lufs=float(np.max(levels[finite_mask])))

        gated = levels[gated_mask]
        p95 = float(np.percentile(gated, 95))
        p10 = float(np.percentile(gated, 10))
        return LRAMetrics(
            lra_lu=p95 - p10,
            max_short_term_lufs=float(np.max(levels[finite_mask])),
        )
