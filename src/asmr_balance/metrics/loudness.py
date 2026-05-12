"""BS.1770-5 integrated loudness reducer.

Consumes :data:`~asmr_balance.graph.types.ZBlock` payloads (one ``(z_l, z_r)``
pair per 100 ms hop) and emits a :class:`LoudnessMetrics` subtree. The two-stage
gating logic (absolute ``-70 LUFS`` per channel, relative ``-10 LU`` from
stereo-combined mean) is ported verbatim from the legacy ``dsp/gating.py`` so
that pyloudnorm parity (``±0.1 LU``) is preserved by construction.

ADR-0004 per-channel semantics: the *single-channel* LUFS uses the per-channel
absolute gate but the *stereo-combined* relative gate threshold — this keeps
the surviving-block mask consistent across the per-channel and stereo paths.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import ClassVar, Final

import numpy as np
from numpy.typing import NDArray

from asmr_balance.graph.types import ZBlock
from asmr_balance.metrics.subtrees import LoudnessMetrics

_LUFS_OFFSET: Final[float] = -0.691  # BS.1770-5 §4.1
_DEFAULT_REL_GATE_DROP_LU: Final[float] = 10.0
_DEFAULT_ABS_GATE_LUFS: Final[float] = -70.0


@dataclass(frozen=True, slots=True)
class GateConfig:
    """Gating thresholds (ADR-0007 — both exposed to CLI / TOML)."""

    abs_gate_lufs: float = _DEFAULT_ABS_GATE_LUFS
    rel_gate_drop_lu: float = _DEFAULT_REL_GATE_DROP_LU


def _loudness_from_z(z: float) -> float:
    """``L = -0.691 + 10·log10(z)``; non-positive or NaN ``z`` → ``-inf``."""
    if z <= 0.0 or not math.isfinite(z):
        return float("-inf")
    return _LUFS_OFFSET + 10.0 * math.log10(z)


def _block_levels(z: NDArray[np.float64]) -> NDArray[np.float64]:
    """Vectorised ``L_block``; non-positive ``z`` → ``-inf``."""
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(z > 0.0, _LUFS_OFFSET + 10.0 * np.log10(z), -np.inf)


def _mean_to_lufs(z: NDArray[np.float64], mask: NDArray[np.bool_]) -> float:
    if not bool(np.any(mask)):
        return float("-inf")
    return _loudness_from_z(float(np.mean(z[mask])))


def _safe_delta(left: float, right: float) -> float:
    """``left − right`` returning NaN when either operand is non-finite."""
    if math.isfinite(left) and math.isfinite(right):
        return left - right
    return float("nan")


@dataclass(slots=True)
class IntegratedLoudnessReducer:
    """``Stream[ZBlock] → LoudnessMetrics``."""

    name: ClassVar[str] = "loudness"

    gate: GateConfig = field(default_factory=GateConfig)
    _z_l: list[float] = field(default_factory=list)
    _z_r: list[float] = field(default_factory=list)

    def update(self, payload: ZBlock) -> None:
        z_l, z_r = payload
        self._z_l.append(z_l)
        self._z_r.append(z_r)

    def finalize(self) -> LoudnessMetrics:
        if not self._z_l:
            inf = float("-inf")
            nan = float("nan")
            return LoudnessMetrics(
                lufs_i_stereo=inf,
                single_channel_lufs_l=inf,
                single_channel_lufs_r=inf,
                single_channel_lufs_ungated_l=inf,
                single_channel_lufs_ungated_r=inf,
                delta_lu=nan,
                delta_lu_ungated=nan,
            )
        z_l = np.asarray(self._z_l, dtype=np.float64)
        z_r = np.asarray(self._z_r, dtype=np.float64)
        z_stereo = z_l + z_r

        ungated_l = _loudness_from_z(float(np.mean(z_l)))
        ungated_r = _loudness_from_z(float(np.mean(z_r)))

        l_blocks = _block_levels(z_l)
        r_blocks = _block_levels(z_r)
        stereo_blocks = _block_levels(z_stereo)

        abs_keep_l = l_blocks >= self.gate.abs_gate_lufs
        abs_keep_r = r_blocks >= self.gate.abs_gate_lufs
        abs_keep_stereo = stereo_blocks >= self.gate.abs_gate_lufs

        if not bool(np.any(abs_keep_stereo)):
            rel_mask_stereo = np.zeros_like(abs_keep_stereo, dtype=bool)
        else:
            mean_z_stereo_abs = float(np.mean(z_stereo[abs_keep_stereo]))
            ref_lufs = _loudness_from_z(mean_z_stereo_abs)
            rel_threshold = ref_lufs - self.gate.rel_gate_drop_lu
            rel_mask_stereo = stereo_blocks >= rel_threshold

        keep_l = abs_keep_l & rel_mask_stereo
        keep_r = abs_keep_r & rel_mask_stereo
        keep_stereo = abs_keep_stereo & rel_mask_stereo

        sc_l = _mean_to_lufs(z_l, keep_l)
        sc_r = _mean_to_lufs(z_r, keep_r)
        return LoudnessMetrics(
            lufs_i_stereo=_mean_to_lufs(z_stereo, keep_stereo),
            single_channel_lufs_l=sc_l,
            single_channel_lufs_r=sc_r,
            single_channel_lufs_ungated_l=ungated_l,
            single_channel_lufs_ungated_r=ungated_r,
            delta_lu=_safe_delta(sc_l, sc_r),
            delta_lu_ungated=_safe_delta(ungated_l, ungated_r),
        )
