"""Top-level metric record and file metadata.

The :class:`MetricRecord` is the per-file forest of typed subtrees that
:mod:`asmr_balance.scan.pipeline` assembles after all reducers finalize. Each
subtree is owned by a single reducer (no shared state, no dict-keyed merge).

A file can have one of three :class:`ScanStatus` outcomes:

* ``ANALYZED`` — full :class:`MetricRecord` with all six subtrees populated.
* ``SKIPPED`` — :class:`MetricRecord` with subtrees absent (``None``); the
  ``meta.skip_reason`` field tells why (mono input, unsupported layout, …).
* ``ERRORED`` — same shape but with ``meta.skip_reason`` set to the error.

The shape (one optional subtree per axis) is chosen so that downstream
consumers (sinks, rules) can pattern-match on ``status`` and only access the
subtrees when ``ANALYZED``.
"""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from asmr_balance.metrics.subtrees import (
    BandImbalanceMetrics,
    DynamicsMetrics,
    LoudnessMetrics,
    LRAMetrics,
    PhaseMetrics,
    SlidingMetrics,
    StereoCorrelationMetrics,
)


class ScanStatus(StrEnum):
    """Outcome of analyzing one file."""

    ANALYZED = "analyzed"
    SKIPPED = "skipped"
    ERRORED = "errored"


class FileMeta(BaseModel):
    """Immutable file-level facts independent of analysis outcome."""

    model_config = ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)

    file_path: Path
    sample_rate: int
    duration_sec: float
    channel_layout: str


class MetricRecord(BaseModel):
    """Per-file metric forest.

    Subtrees are ``None`` when ``status`` is ``SKIPPED`` or ``ERRORED``.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    meta: FileMeta
    status: ScanStatus
    skip_reason: str | None = None
    loudness: LoudnessMetrics | None = None
    lra: LRAMetrics | None = None
    correlation: StereoCorrelationMetrics | None = None
    band: BandImbalanceMetrics | None = None
    sliding: SlidingMetrics | None = None
    phase: PhaseMetrics | None = None
    dynamics: DynamicsMetrics | None = None
