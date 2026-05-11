"""Online L/R correlation + Mid/Side analyzer.

Reuses ``WelfordCorrelation`` and ``MidSideRMS`` (ADR-0001) so the stream is
visited only once.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from asmr_balance.dsp.correlation import StereoStats

if TYPE_CHECKING:
    from asmr_balance.types import StereoBlock


class CorrelationImbalanceAnalyzer:
    """Emits ``pearson_r`` and ``ms_ratio_db``."""

    name: ClassVar[str] = "correlation_imbalance"

    __slots__ = ("_stats",)

    def __init__(self) -> None:
        self._stats = StereoStats()

    def push(self, block: StereoBlock) -> None:
        if block.size == 0:
            return
        self._stats.update(block[:, 0], block[:, 1])

    def finalize(self) -> dict[str, float]:
        return {
            "pearson_r": self._stats.correlation.correlation,
            "ms_ratio_db": self._stats.mid_side.ms_ratio_db,
        }
