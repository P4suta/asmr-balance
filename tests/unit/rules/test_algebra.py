"""Tests for the rule evaluation fold."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar

from asmr_balance.algebra.semilattice import Verdict
from asmr_balance.metrics.record import FileMeta, MetricRecord, ScanStatus
from asmr_balance.metrics.subtrees import LoudnessMetrics
from asmr_balance.rules.algebra import Flag, evaluate
from asmr_balance.rules.thresholds import LrBalanceThresholds, ThresholdSet


def _meta() -> FileMeta:
    return FileMeta(
        file_path=Path("/tmp/x.wav"),
        sample_rate=48000,
        duration_sec=1.0,
        channel_layout="stereo",
    )


def _loud(delta: float = 0.0) -> LoudnessMetrics:
    return LoudnessMetrics(
        lufs_i_stereo=-14.0,
        single_channel_lufs_l=-17.0 + delta / 2,
        single_channel_lufs_r=-17.0 - delta / 2,
        single_channel_lufs_ungated_l=-17.0,
        single_channel_lufs_ungated_r=-17.0,
        delta_lu=delta,
        delta_lu_ungated=delta,
    )


@dataclass(frozen=True, slots=True)
class _FailRule:
    """Stub rule that always emits Verdict.FAIL."""

    code: str = "ALWAYS_FAIL"
    severity_ceiling: ClassVar[Verdict] = Verdict.FAIL
    metric_path: ClassVar[str] = "loudness"
    threshold_path: ClassVar[str] = "lr_balance"

    def judge(
        self,
        m: LoudnessMetrics,  # noqa: ARG002
        t: LrBalanceThresholds,  # noqa: ARG002
    ) -> Flag | None:
        return Flag(code=self.code, severity=Verdict.FAIL, message="forced")


@dataclass(frozen=True, slots=True)
class _NeverRule:
    """Stub rule that never fires."""

    code: str = "NEVER"
    severity_ceiling: ClassVar[Verdict] = Verdict.WARN
    metric_path: ClassVar[str] = "loudness"
    threshold_path: ClassVar[str] = "lr_balance"

    def judge(
        self,
        m: LoudnessMetrics,  # noqa: ARG002
        t: LrBalanceThresholds,  # noqa: ARG002
    ) -> Flag | None:
        return None


def test_evaluate_empty_ruleset_returns_ok() -> None:
    rec = MetricRecord(meta=_meta(), status=ScanStatus.ANALYZED, loudness=_loud())
    res = evaluate((), rec, ThresholdSet())
    assert res.flags == ()
    assert res.verdict is Verdict.OK


def test_evaluate_aggregates_via_join() -> None:
    rules = (_FailRule(), _NeverRule(), _FailRule())
    rec = MetricRecord(meta=_meta(), status=ScanStatus.ANALYZED, loudness=_loud())
    res = evaluate(rules, rec, ThresholdSet())
    assert res.verdict is Verdict.FAIL
    assert len(res.flags) == 2


def test_evaluate_skipped_record_returns_no_flags() -> None:
    rec = MetricRecord(
        meta=_meta(),
        status=ScanStatus.SKIPPED,
        skip_reason="mono",
        loudness=None,
    )
    res = evaluate((_FailRule(),), rec, ThresholdSet())
    assert res.flags == ()
    assert res.verdict is Verdict.OK


def test_evaluate_errored_record_returns_no_flags() -> None:
    rec = MetricRecord(meta=_meta(), status=ScanStatus.ERRORED, skip_reason="ValueError: bad")
    res = evaluate((_FailRule(),), rec, ThresholdSet())
    assert res.flags == ()


def test_evaluate_skips_rule_when_subtree_is_none() -> None:
    """Rules requesting an absent subtree are silently skipped (defensive)."""
    rec = MetricRecord(meta=_meta(), status=ScanStatus.ANALYZED, loudness=None)
    res = evaluate((_FailRule(),), rec, ThresholdSet())
    assert res.flags == ()
