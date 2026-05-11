"""Band-imbalance analyzer (ADR-0006)."""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from asmr_balance.dsp.bands import Band, BandImbalanceAccumulator

if TYPE_CHECKING:
    from asmr_balance.types import StereoBlock


class BandImbalanceAnalyzer:
    """Emits per-band L/R energy ratio (dB) for the 4 standard bands."""

    name: ClassVar[str] = "band_imbalance"

    __slots__ = ("_acc",)

    def __init__(self, sample_rate: int) -> None:
        self._acc = BandImbalanceAccumulator(sample_rate=sample_rate)

    def push(self, block: StereoBlock) -> None:
        if block.size == 0:
            return
        self._acc.push(block[:, 0], block[:, 1])

    def finalize(self) -> dict[str, float]:
        return {
            "band_imbalance_low": self._acc.imbalance_db(Band.LOW),
            "band_imbalance_low_mid": self._acc.imbalance_db(Band.LOW_MID),
            "band_imbalance_high_mid": self._acc.imbalance_db(Band.HIGH_MID),
            "band_imbalance_high": self._acc.imbalance_db(Band.HIGH),
        }
