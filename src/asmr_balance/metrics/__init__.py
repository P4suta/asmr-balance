"""Metric subtrees and their streaming reducers.

Each module in this package contributes one or more typed
:class:`~asmr_balance.algebra.reducer.Reducer` implementations together with
the immutable subtree they emit. The pipeline composes the subtrees into the
top-level :class:`~asmr_balance.metrics.record.MetricRecord` after all
reducers have been finalised.

Modules:

* :mod:`asmr_balance.metrics.subtrees` — typed subtree dataclasses
* :mod:`asmr_balance.metrics.record` — :class:`MetricRecord`, :class:`FileMeta`
* :mod:`asmr_balance.metrics.loudness` — BS.1770-5 integrated loudness
* :mod:`asmr_balance.metrics.lra` — EBU R128 loudness range
* :mod:`asmr_balance.metrics.sliding` — per-block ΔLU statistics
* :mod:`asmr_balance.metrics.correlation` — Welford Pearson + mid-side energy
* :mod:`asmr_balance.metrics.band` — 31 1/3-octave imbalances + 4-band roll-up
* :mod:`asmr_balance.metrics.phase` — low-band phase coherence
* :mod:`asmr_balance.metrics.dynamics` — true peak + PSR derivation
"""

from __future__ import annotations

from asmr_balance.metrics.band import BandImbalanceReducer
from asmr_balance.metrics.correlation import StereoCorrelationReducer
from asmr_balance.metrics.dynamics import TruePeakReducer, derive_psr_db
from asmr_balance.metrics.loudness import GateConfig, IntegratedLoudnessReducer
from asmr_balance.metrics.lra import LRAReducer
from asmr_balance.metrics.phase import LowPhaseCoherenceReducer
from asmr_balance.metrics.record import FileMeta, MetricRecord, ScanStatus
from asmr_balance.metrics.sliding import SlidingImbalanceReducer
from asmr_balance.metrics.subtrees import (
    BandImbalanceMetrics,
    DynamicsMetrics,
    LoudnessMetrics,
    LRAMetrics,
    PhaseMetrics,
    SlidingMetrics,
    StereoCorrelationMetrics,
)

__all__ = [
    "BandImbalanceMetrics",
    "BandImbalanceReducer",
    "DynamicsMetrics",
    "FileMeta",
    "GateConfig",
    "IntegratedLoudnessReducer",
    "LRAMetrics",
    "LRAReducer",
    "LoudnessMetrics",
    "LowPhaseCoherenceReducer",
    "MetricRecord",
    "PhaseMetrics",
    "ScanStatus",
    "SlidingImbalanceReducer",
    "SlidingMetrics",
    "StereoCorrelationMetrics",
    "StereoCorrelationReducer",
    "TruePeakReducer",
    "derive_psr_db",
]
