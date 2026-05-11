"""LUFS imbalance analyzer: wraps ``LufsAccumulator`` and emits ``delta_lu``."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, ClassVar

from asmr_balance.dsp.gating import GateConfig
from asmr_balance.dsp.lufs import LufsAccumulator

if TYPE_CHECKING:
    from asmr_balance.types import StereoBlock


class LufsImbalanceAnalyzer:
    """Computes BS.1770 ``LUFS_I_stereo`` + per-channel ``single_channel_lufs``."""

    name: ClassVar[str] = "lufs_imbalance"

    __slots__ = ("_acc",)

    def __init__(self, sample_rate: int, gate_lufs: float = -70.0) -> None:
        self._acc = LufsAccumulator(
            sample_rate=sample_rate,
            gate=GateConfig(abs_gate_lufs=gate_lufs),
        )

    def push(self, block: StereoBlock) -> None:
        self._acc.push(block)

    def finalize(self) -> dict[str, float]:
        metrics = self._acc.finalize()
        left = metrics["single_channel_lufs_l"]
        right = metrics["single_channel_lufs_r"]
        left_u = metrics["single_channel_lufs_ungated_l"]
        right_u = metrics["single_channel_lufs_ungated_r"]
        metrics["delta_lu"] = _safe_delta(left, right)
        metrics["delta_lu_ungated"] = _safe_delta(left_u, right_u)
        return metrics


def _safe_delta(left: float, right: float) -> float:
    """``left - right`` propagating ``-inf`` to ``nan`` (one-sided silence)."""
    if math.isinf(left) and math.isinf(right):
        return float("nan")
    if math.isinf(left) or math.isinf(right):
        return float("nan")
    return left - right
