"""Compatibility helpers for tests authored against the legacy API surface.

The redesign replaces ``dsp.lufs.measure_lufs`` with the typed
:class:`asmr_balance.metrics.loudness.IntegratedLoudnessReducer` driven by
the signal graph. To preserve the black-box guarantees of the legacy
property + regression suites (BS.1770 invariants, ``±0.1 LU`` pyloudnorm
parity), this module provides a tiny adapter that builds a single-purpose
graph and returns the same ``dict[str, float]`` shape as the legacy helper.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

from asmr_balance.graph.builder import GraphBuilder
from asmr_balance.graph.scheduler import run_from_iter
from asmr_balance.graph.types import RawBlock
from asmr_balance.metrics.loudness import GateConfig, IntegratedLoudnessReducer

if TYPE_CHECKING:
    from numpy.typing import NDArray


def measure_lufs(
    samples: NDArray[np.float32], sample_rate: int, *, gate_lufs: float = -70.0
) -> dict[str, float]:
    """Adapter — drive a minimal loudness graph and project to a flat dict.

    Mirrors the legacy ``asmr_balance.dsp.lufs.measure_lufs`` signature so
    legacy property / regression tests can keep their original semantics.
    """
    g = GraphBuilder()
    raw = g.source()
    kw = g.kweight(raw, sample_rate=sample_rate)
    z = g.zblocks(kw, sample_rate=sample_rate)
    g.reduce(
        "loudness",
        IntegratedLoudnessReducer(gate=GateConfig(abs_gate_lufs=gate_lufs)),
        z,
    )
    frozen = g.freeze()
    block_size = max(1, int(sample_rate * 0.1))
    blocks: list[RawBlock] = []
    for start in range(0, samples.shape[0], block_size):
        end = min(start + block_size, samples.shape[0])
        chunk = np.ascontiguousarray(samples[start:end], dtype=np.float32)
        blocks.append(RawBlock(chunk))
    result = run_from_iter(frozen, blocks)["loudness"]
    return {
        "lufs_i_stereo": result.lufs_i_stereo,
        "single_channel_lufs_l": result.single_channel_lufs_l,
        "single_channel_lufs_r": result.single_channel_lufs_r,
        "single_channel_lufs_ungated_l": result.single_channel_lufs_ungated_l,
        "single_channel_lufs_ungated_r": result.single_channel_lufs_ungated_r,
    }
