"""Streaming LUFS accumulator: K-weighting + per-channel block ``z`` + gating.

Provides the high-level ``LufsAccumulator`` consumed by analyzers via the
streaming Protocol (ADR-0001). Each ``push(block)`` accepts an arbitrary chunk
of stereo PCM and updates per-channel state; ``finalize()`` returns:

- ``lufs_i_stereo``       — BS.1770-5 spec-compliant integrated loudness
- ``single_channel_lufs_{l,r}`` — per-channel gated KGM (ADR-0004, spec-外)
- ``single_channel_lufs_ungated_{l,r}`` — gate-free fallback (ADR-0007)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import numpy as np

from asmr_balance.dsp.gating import BlockAccumulator, GateConfig, integrate_gated
from asmr_balance.dsp.kweight import apply_kweighting, make_kweighting_sos
from asmr_balance.types import STEREO_CHANNELS, StereoBlock

if TYPE_CHECKING:
    from numpy.typing import NDArray


@dataclass(slots=True)
class LufsAccumulator:
    """Streaming-friendly LUFS accumulator (one per file)."""

    sample_rate: int
    gate: GateConfig = field(default_factory=GateConfig)
    _sos: NDArray[np.float64] = field(init=False)
    _zi_l: NDArray[np.float64] | None = field(default=None, init=False)
    _zi_r: NDArray[np.float64] | None = field(default=None, init=False)
    _acc_l: BlockAccumulator = field(init=False)
    _acc_r: BlockAccumulator = field(init=False)
    _initialised: bool = field(default=False, init=False)

    def __post_init__(self) -> None:
        self._sos = make_kweighting_sos(self.sample_rate)
        self._acc_l = BlockAccumulator(sample_rate=self.sample_rate)
        self._acc_r = BlockAccumulator(sample_rate=self.sample_rate)

    def push(self, block: StereoBlock) -> None:
        """Consume a stereo block (shape ``(N, 2)``, float-like, contiguous)."""
        if block.ndim != 2 or block.shape[1] != STEREO_CHANNELS:
            msg = f"expected stereo (N, 2), got shape {block.shape}"
            raise ValueError(msg)
        if block.shape[0] == 0:
            return
        left = block[:, 0]
        right = block[:, 1]
        l_kw, self._zi_l = apply_kweighting(left, self._sos, self._zi_l)
        r_kw, self._zi_r = apply_kweighting(right, self._sos, self._zi_r)
        self._initialised = True
        self._acc_l.push(l_kw)
        self._acc_r.push(r_kw)

    def finalize(self) -> dict[str, float]:
        """Return the full LUFS metric dict (see module docstring)."""
        return integrate_gated(
            self._acc_l.z_blocks,
            self._acc_r.z_blocks,
            self.gate,
        )

    @property
    def block_count(self) -> int:
        """Number of 400 ms blocks produced so far (after current ``push`` calls)."""
        return len(self._acc_l.z_blocks)


def measure_lufs(
    stereo: NDArray[np.floating],
    sample_rate: int,
    gate: GateConfig | None = None,
) -> dict[str, float]:
    """Convenience: run the full pipeline on an in-memory stereo array.

    Args:
        stereo: Shape ``(N, 2)``, any floating dtype.
        sample_rate: Hz.
        gate: Custom gate thresholds; defaults to spec-compliant ``-70 LUFS``.

    Returns:
        Same dict as ``LufsAccumulator.finalize``.
    """
    acc = LufsAccumulator(sample_rate=sample_rate, gate=gate or GateConfig())
    acc.push(np.ascontiguousarray(stereo, dtype=np.float32))
    return acc.finalize()
