"""Sliding-window per-block ΔLU statistics.

Reuses the K-weighting + 400 ms block accumulator from ``dsp.lufs`` but skips
the two-stage gating: we want a per-block view of L/R loudness *difference*
so that local imbalances ("front-half loud-L, back-half loud-R") surface even
when the integrated ``delta_lu`` is near zero.

Per-block ``L_block_ch = -0.691 + 10·log10(z_ch_block)``; blocks where either
side is ≤ 0 (silent) are dropped (kept in the underlying ``z`` arrays but
filtered before statistics).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import numpy as np

from asmr_balance.dsp.gating import _block_levels
from asmr_balance.dsp.lufs import LufsAccumulator

if TYPE_CHECKING:
    from asmr_balance.types import StereoBlock

_HOP_SEC: float = 0.1


@dataclass(slots=True)
class SlidingImbalance:
    """Per-block ΔLU collector that exposes summary statistics on ``finalize``."""

    sample_rate: int
    _lufs: LufsAccumulator = field(init=False)

    def __post_init__(self) -> None:
        self._lufs = LufsAccumulator(sample_rate=self.sample_rate)

    def push(self, block: StereoBlock) -> None:
        if block.size == 0:
            return
        self._lufs.push(block)

    def finalize(self) -> dict[str, float]:
        z_l = np.asarray(self._lufs._acc_l.z_blocks, dtype=np.float64)  # noqa: SLF001
        z_r = np.asarray(self._lufs._acc_r.z_blocks, dtype=np.float64)  # noqa: SLF001
        if z_l.size == 0:
            return _empty()
        l_levels = _block_levels(z_l)
        r_levels = _block_levels(z_r)
        valid = np.isfinite(l_levels) & np.isfinite(r_levels)
        if not np.any(valid):
            return _empty()
        delta = l_levels[valid] - r_levels[valid]
        abs_delta = np.abs(delta)
        max_idx = int(np.argmax(abs_delta))
        # Position in the full block sequence (account for filtering)
        original_positions = np.flatnonzero(valid)
        t_max_block = int(original_positions[max_idx])
        return {
            "sliding_max_lu": float(abs_delta.max()),
            "sliding_p95_lu": float(np.percentile(abs_delta, 95)),
            "sliding_std_lu": float(np.std(delta)),
            "sliding_t_max_sec": t_max_block * _HOP_SEC,
        }


def _empty() -> dict[str, float]:
    return {
        "sliding_max_lu": float("nan"),
        "sliding_p95_lu": float("nan"),
        "sliding_std_lu": float("nan"),
        "sliding_t_max_sec": float("nan"),
    }
