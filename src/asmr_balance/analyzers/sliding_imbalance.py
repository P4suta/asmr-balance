"""Sliding-window ΔLU analyzer."""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from asmr_balance.dsp.sliding import SlidingImbalance

if TYPE_CHECKING:
    from asmr_balance.types import StereoBlock


class SlidingImbalanceAnalyzer:
    """Per-block ``delta_lu`` summary statistics (``max``, ``p95``, ``std``, ``t_max``)."""

    name: ClassVar[str] = "sliding_imbalance"

    __slots__ = ("_acc",)

    def __init__(self, sample_rate: int) -> None:
        self._acc = SlidingImbalance(sample_rate=sample_rate)

    def push(self, block: StereoBlock) -> None:
        self._acc.push(block)

    def finalize(self) -> dict[str, float]:
        return self._acc.finalize()
