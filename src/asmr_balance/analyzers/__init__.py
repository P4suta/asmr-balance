"""Analyzer registry — protocol + factory list (ADR-0001).

Each analyzer is constructed per file via ``build_analyzers(config, sample_rate)``
and consumed by ``pipeline.scan_one`` via ``push(block)`` / ``finalize()``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar, Protocol

if TYPE_CHECKING:
    from asmr_balance.config import Config
    from asmr_balance.types import StereoBlock


class Analyzer(Protocol):
    """Streaming, stateful, single-file consumer."""

    name: ClassVar[str]

    def push(self, block: StereoBlock) -> None: ...

    def finalize(self) -> dict[str, float]: ...


def build_analyzers(config: Config, sample_rate: int) -> list[Analyzer]:
    """Construct the default analyzer set for one file."""
    from asmr_balance.analyzers.band_imbalance import BandImbalanceAnalyzer
    from asmr_balance.analyzers.correlation_imbalance import CorrelationImbalanceAnalyzer
    from asmr_balance.analyzers.lufs_imbalance import LufsImbalanceAnalyzer
    from asmr_balance.analyzers.phase_coherence import PhaseCoherenceAnalyzer
    from asmr_balance.analyzers.sliding_imbalance import SlidingImbalanceAnalyzer

    return [
        LufsImbalanceAnalyzer(sample_rate=sample_rate, gate_lufs=config.gate_lufs),
        CorrelationImbalanceAnalyzer(),
        BandImbalanceAnalyzer(sample_rate=sample_rate),
        SlidingImbalanceAnalyzer(sample_rate=sample_rate),
        PhaseCoherenceAnalyzer(sample_rate=sample_rate),
    ]
