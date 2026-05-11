"""Low-band phase coherence analyzer."""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from asmr_balance.dsp.phase import LowPhaseCoherence

if TYPE_CHECKING:
    from asmr_balance.types import StereoBlock


class PhaseCoherenceAnalyzer:
    """Emits ``low_phase_coherence`` (Pearson r of <300 Hz L and R)."""

    name: ClassVar[str] = "phase_coherence"

    __slots__ = ("_acc",)

    def __init__(self, sample_rate: int) -> None:
        self._acc = LowPhaseCoherence(sample_rate=sample_rate)

    def push(self, block: StereoBlock) -> None:
        self._acc.push(block)

    def finalize(self) -> dict[str, float]:
        return {"low_phase_coherence": self._acc.finalize()}
