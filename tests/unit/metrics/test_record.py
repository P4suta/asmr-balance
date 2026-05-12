"""Tests for :class:`MetricRecord`."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from asmr_balance.metrics.record import FileMeta, MetricRecord, ScanStatus
from asmr_balance.metrics.subtrees import LoudnessMetrics


def _meta() -> FileMeta:
    return FileMeta(
        file_path=Path("/tmp/test.wav"),
        sample_rate=48000,
        duration_sec=10.0,
        channel_layout="stereo",
    )


def test_skipped_record_has_no_subtrees() -> None:
    rec = MetricRecord(meta=_meta(), status=ScanStatus.SKIPPED, skip_reason="mono input")
    assert rec.loudness is None
    assert rec.lra is None
    assert rec.band is None


def test_analyzed_record_accepts_subtrees() -> None:
    loud = LoudnessMetrics(
        lufs_i_stereo=-14.0,
        single_channel_lufs_l=-17.0,
        single_channel_lufs_r=-17.0,
        single_channel_lufs_ungated_l=-17.0,
        single_channel_lufs_ungated_r=-17.0,
        delta_lu=0.0,
        delta_lu_ungated=0.0,
    )
    rec = MetricRecord(meta=_meta(), status=ScanStatus.ANALYZED, loudness=loud)
    assert rec.loudness is not None
    assert rec.loudness.lufs_i_stereo == -14.0


def test_metric_record_is_frozen() -> None:
    rec = MetricRecord(meta=_meta(), status=ScanStatus.SKIPPED)
    with pytest.raises(ValidationError):
        rec.status = ScanStatus.ANALYZED  # type: ignore[misc]


def test_metric_record_forbids_extra_fields() -> None:
    with pytest.raises(ValidationError):
        MetricRecord(meta=_meta(), status=ScanStatus.SKIPPED, mystery="x")  # type: ignore[call-arg]
