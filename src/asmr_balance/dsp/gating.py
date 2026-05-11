"""ITU-R BS.1770-5 block accumulation + two-stage gating.

A streaming-friendly accumulator that consumes already-K-weighted samples in
arbitrary chunk sizes and emits 400 ms blocks of mean-square (``z``) values
spaced by 100 ms (75 % overlap, per spec).

Gating semantics (ADR-0004):
- **absolute gate** (``-70 LUFS`` by default): applied **per-channel** to
  ``L_block_ch = -0.691 + 10·log10(z_ch_block)``;
- **relative gate** (``mean − 10 LU``): applied with a **stereo-combined**
  reference (``L_block_stereo = -0.691 + 10·log10(z_l + z_r)``), so the same
  surviving-block mask is used for both single-channel and stereo aggregation.

Both gate thresholds are exposed via ``GateConfig`` (ADR-0007).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Final

import numpy as np

if TYPE_CHECKING:
    from collections.abc import Sequence

    from numpy.typing import NDArray

_BLOCK_DURATION_SEC: Final[float] = 0.4
_HOP_DURATION_SEC: Final[float] = 0.1
_LUFS_OFFSET: Final[float] = -0.691  # ITU-R BS.1770-5 §4.1
_REL_GATE_DROP_LU: Final[float] = 10.0


@dataclass(frozen=True, slots=True)
class GateConfig:
    """Gating thresholds (ADR-0007)."""

    abs_gate_lufs: float = -70.0
    rel_gate_drop_lu: float = _REL_GATE_DROP_LU


def loudness_from_z(z: float) -> float:
    """Convert per-block mean-square ``z`` to a LUFS-like dB scalar.

    Returns ``-inf`` when ``z <= 0``. Matches BS.1770 ``L = -0.691 + 10·log10(z)``.
    """
    if z <= 0.0 or not math.isfinite(z):
        return float("-inf")
    return _LUFS_OFFSET + 10.0 * math.log10(z)


def integrated_from_z_mean(z_mean: float) -> float:
    """Same offset/log conversion for an integrated mean."""
    return loudness_from_z(z_mean)


@dataclass(slots=True)
class BlockAccumulator:
    """Streaming 400 ms / 100 ms-hop block builder for K-weighted samples.

    Push chunks of arbitrary size; once enough samples have arrived, the
    accumulator emits one ``z`` per 400 ms block.  Excess samples are retained
    in the internal buffer.

    Use one accumulator per channel.
    """

    sample_rate: int
    _block_size: int = field(init=False)
    _hop_size: int = field(init=False)
    _buffer: list[NDArray[np.float64]] = field(default_factory=list, init=False)
    _buffer_len: int = field(default=0, init=False)
    z_blocks: list[float] = field(default_factory=list, init=False)

    def __post_init__(self) -> None:
        if self.sample_rate <= 0:
            msg = f"sample_rate must be positive, got {self.sample_rate}"
            raise ValueError(msg)
        self._block_size = round(self.sample_rate * _BLOCK_DURATION_SEC)
        self._hop_size = round(self.sample_rate * _HOP_DURATION_SEC)

    @property
    def block_size(self) -> int:
        return self._block_size

    @property
    def hop_size(self) -> int:
        return self._hop_size

    def push(self, samples: NDArray[np.floating]) -> None:
        """Append already-K-weighted ``samples`` and emit any newly-complete blocks."""
        if samples.size == 0:
            return
        self._buffer.append(np.asarray(samples, dtype=np.float64))
        self._buffer_len += samples.size
        self._drain()

    def _drain(self) -> None:
        if self._buffer_len < self._block_size:
            return
        joined = np.concatenate(self._buffer)
        pos = 0
        block = self._block_size
        hop = self._hop_size
        while pos + block <= joined.size:
            window = joined[pos : pos + block]
            z = float(np.mean(window * window))
            self.z_blocks.append(z)
            pos += hop
        tail = joined[pos:]
        self._buffer = [tail] if tail.size > 0 else []
        self._buffer_len = tail.size


_DEFAULT_GATE = GateConfig()


def integrate_gated(
    z_blocks_l: Sequence[float],
    z_blocks_r: Sequence[float],
    cfg: GateConfig | None = None,
) -> dict[str, float]:
    """Apply BS.1770 two-stage gating to per-block ``z`` lists.

    Returns a dict with keys:
        - ``lufs_i_stereo``: spec-compliant integrated loudness.
        - ``single_channel_lufs_l/_r``: per-channel gated mean (ADR-0004).
        - ``single_channel_lufs_ungated_l/_r``: gate-free fallback (ADR-0007).

    All values are ``float("-inf")`` when their respective mean ``z`` is ≤ 0.
    """
    if cfg is None:
        cfg = _DEFAULT_GATE
    z_l = np.asarray(z_blocks_l, dtype=np.float64)
    z_r = np.asarray(z_blocks_r, dtype=np.float64)
    if z_l.size != z_r.size:
        msg = f"per-channel block counts differ: {z_l.size} vs {z_r.size}"
        raise ValueError(msg)
    n = z_l.size
    if n == 0:
        return {
            "lufs_i_stereo": float("-inf"),
            "single_channel_lufs_l": float("-inf"),
            "single_channel_lufs_r": float("-inf"),
            "single_channel_lufs_ungated_l": float("-inf"),
            "single_channel_lufs_ungated_r": float("-inf"),
        }

    z_stereo = z_l + z_r

    # --- ungated fallback ------------------------------------------------
    ungated_l = integrated_from_z_mean(float(np.mean(z_l)))
    ungated_r = integrated_from_z_mean(float(np.mean(z_r)))

    # --- absolute gate per channel (single-channel path, ADR-0004) -------
    l_blocks = _block_levels(z_l)
    r_blocks = _block_levels(z_r)
    stereo_blocks = _block_levels(z_stereo)

    abs_keep_l = l_blocks >= cfg.abs_gate_lufs
    abs_keep_r = r_blocks >= cfg.abs_gate_lufs
    abs_keep_stereo = stereo_blocks >= cfg.abs_gate_lufs

    # --- relative gate (stereo-combined reference, ADR-0004) -------------
    if not np.any(abs_keep_stereo):
        rel_mask_stereo = np.zeros_like(abs_keep_stereo, dtype=bool)
    else:
        mean_z_stereo_abs = float(np.mean(z_stereo[abs_keep_stereo]))
        ref_lufs = integrated_from_z_mean(mean_z_stereo_abs)
        rel_threshold = ref_lufs - cfg.rel_gate_drop_lu
        rel_mask_stereo = stereo_blocks >= rel_threshold

    keep_l = abs_keep_l & rel_mask_stereo
    keep_r = abs_keep_r & rel_mask_stereo
    keep_stereo = abs_keep_stereo & rel_mask_stereo

    return {
        "lufs_i_stereo": _mean_to_lufs(z_stereo, keep_stereo),
        "single_channel_lufs_l": _mean_to_lufs(z_l, keep_l),
        "single_channel_lufs_r": _mean_to_lufs(z_r, keep_r),
        "single_channel_lufs_ungated_l": ungated_l,
        "single_channel_lufs_ungated_r": ungated_r,
    }


def _block_levels(z: NDArray[np.float64]) -> NDArray[np.float64]:
    """Vectorised ``L_block = -0.691 + 10·log10(z)``; non-positive ``z`` → ``-inf``."""
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(z > 0.0, _LUFS_OFFSET + 10.0 * np.log10(z), -np.inf)


def _mean_to_lufs(z: NDArray[np.float64], mask: NDArray[np.bool_]) -> float:
    if not np.any(mask):
        return float("-inf")
    return integrated_from_z_mean(float(np.mean(z[mask])))
