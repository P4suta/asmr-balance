from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from asmr_balance.algebra.semilattice import Verdict
from asmr_balance.config.model import Config
from asmr_balance.metrics.record import FileMeta, MetricRecord, ScanStatus
from asmr_balance.rules.algebra import Flag
from asmr_balance.scan.pipeline import FileResult, scan_one
from asmr_balance.web.views.diagnosis import (
    Diagnosis,
    Finding,
    diagnose,
)


def _wrap_with_flag(result: FileResult, flag: Flag, verdict: Verdict) -> FileResult:
    return replace(result, flags=(flag,), verdict=verdict)


# ---------------------------------------------------------------------------
# headline + summary
# ---------------------------------------------------------------------------
def test_ok_result_yields_ok_headline(balanced_wav: Path) -> None:
    result = scan_one(balanced_wav, Config().with_overrides(workers=1))
    # Balanced wav fires PSEUDO_MONO (WARN). Strip flags to make it a true OK.
    clean = replace(result, flags=(), verdict=Verdict.OK)
    d = diagnose(clean)
    assert d.verdict is Verdict.OK
    assert d.headline.startswith("✅")
    assert "問題なし" in d.headline or "問題なし" in d.summary
    assert d.findings == ()
    assert d.is_analyzable


def test_fail_result_yields_fail_headline(panned_wav: Path) -> None:
    result = scan_one(panned_wav, Config().with_overrides(workers=1))
    d = diagnose(result)
    assert d.verdict is Verdict.FAIL
    assert d.headline.startswith("✗")
    assert d.findings  # at least one
    # Top finding is the most severe (FAIL).
    assert any(f.severity is Verdict.FAIL for f in d.findings)


def test_warn_summary_mentions_count(balanced_wav: Path) -> None:
    result = scan_one(balanced_wav, Config().with_overrides(workers=1))
    # Force a WARN-only firing.
    flag = Flag(code="PSEUDO_MONO", severity=Verdict.WARN, message="Pearson r=1.000")
    wrapped = _wrap_with_flag(result, flag, Verdict.WARN)
    d = diagnose(wrapped)
    assert d.verdict is Verdict.WARN
    assert "1 件" in d.summary


# ---------------------------------------------------------------------------
# per-flag interpreters cover every Builder branch
# ---------------------------------------------------------------------------
def test_lr_balance_finding_includes_direction(panned_wav: Path) -> None:
    result = scan_one(panned_wav, Config().with_overrides(workers=1))
    flag = Flag(code="LR_BALANCE_FAIL", severity=Verdict.FAIL, message="|ΔLU|=12.00 ≥ 6.0")
    wrapped = _wrap_with_flag(result, flag, Verdict.FAIL)
    finding = diagnose(wrapped).findings[0]
    assert "L" in finding.title or "R" in finding.title
    assert "12.0" in finding.explanation or "12.00" in finding.explanation
    assert finding.technical_ref == f"{flag.code} · {flag.message}"


def test_local_bias_finding_includes_time_marker(panned_wav: Path) -> None:
    result = scan_one(panned_wav, Config().with_overrides(workers=1))
    flag = Flag(code="LOCAL_BIAS_FAIL", severity=Verdict.FAIL, message="p95=10.0")
    wrapped = _wrap_with_flag(result, flag, Verdict.FAIL)
    finding = diagnose(wrapped).findings[0]
    assert "区間" in finding.title or "局所" in finding.explanation


def test_pseudo_mono_finding_quotes_pearson(balanced_wav: Path) -> None:
    result = scan_one(balanced_wav, Config().with_overrides(workers=1))
    flag = Flag(code="PSEUDO_MONO", severity=Verdict.WARN, message="r=1.000")
    wrapped = _wrap_with_flag(result, flag, Verdict.WARN)
    finding = diagnose(wrapped).findings[0]
    assert "擬似モノラル" in finding.title or "ステレオ" in finding.title
    assert "相関" in finding.explanation


def test_phase_inv_finding(balanced_wav: Path) -> None:
    result = scan_one(balanced_wav, Config().with_overrides(workers=1))
    flag = Flag(code="PHASE_INV_WARN", severity=Verdict.WARN, message="coh=-0.5")
    wrapped = _wrap_with_flag(result, flag, Verdict.WARN)
    finding = diagnose(wrapped).findings[0]
    assert "位相" in finding.title


def test_mid_side_narrow_finding(balanced_wav: Path) -> None:
    result = scan_one(balanced_wav, Config().with_overrides(workers=1))
    flag = Flag(code="MID_SIDE_NARROW", severity=Verdict.WARN, message="M/S=15dB")
    wrapped = _wrap_with_flag(result, flag, Verdict.WARN)
    finding = diagnose(wrapped).findings[0]
    assert "ステレオ" in finding.title or "Side" in finding.title


def test_band_bias_finding_labels_each_slot(balanced_wav: Path) -> None:
    result = scan_one(balanced_wav, Config().with_overrides(workers=1))
    for code in ("BAND_BIAS_LOW", "BAND_BIAS_LOW_MID", "BAND_BIAS_HIGH_MID", "BAND_BIAS_HIGH"):
        flag = Flag(code=code, severity=Verdict.WARN, message=f"{code}=6dB")
        wrapped = _wrap_with_flag(result, flag, Verdict.WARN)
        finding = diagnose(wrapped).findings[0]
        # Title should mention "L/R 偏り" along with a frequency-range label.
        assert "偏り" in finding.title


def test_true_peak_finding_warn_vs_fail(panned_wav: Path) -> None:
    result = scan_one(panned_wav, Config().with_overrides(workers=1))
    warn_flag = Flag(code="TRUE_PEAK_WARN", severity=Verdict.WARN, message="-0.5 dBTP")
    fail_flag = Flag(code="TRUE_PEAK_FAIL", severity=Verdict.FAIL, message="+0.2 dBTP")
    warn_finding = diagnose(_wrap_with_flag(result, warn_flag, Verdict.WARN)).findings[0]
    fail_finding = diagnose(_wrap_with_flag(result, fail_flag, Verdict.FAIL)).findings[0]
    assert "可能性" in warn_finding.explanation
    assert "確実" in fail_finding.explanation


def test_gate_reject_finding() -> None:
    meta = FileMeta(
        file_path=Path("/tmp/x.wav"),
        sample_rate=48000,
        duration_sec=1.0,
        channel_layout="stereo",
    )
    record = MetricRecord(meta=meta, status=ScanStatus.ANALYZED)
    flag = Flag(code="GATE_REJECT_ALL", severity=Verdict.WARN, message="L gated")
    result = FileResult(record=record, flags=(flag,), verdict=Verdict.WARN, elapsed_sec=0.1)
    finding = diagnose(result).findings[0]
    assert "無音" in finding.title or "極小" in finding.title


def test_unknown_flag_falls_back_to_generic() -> None:
    meta = FileMeta(
        file_path=Path("/tmp/x.wav"),
        sample_rate=48000,
        duration_sec=1.0,
        channel_layout="stereo",
    )
    record = MetricRecord(meta=meta, status=ScanStatus.ANALYZED)
    flag = Flag(code="UNKNOWN_RULE", severity=Verdict.WARN, message="future rule")
    result = FileResult(record=record, flags=(flag,), verdict=Verdict.WARN, elapsed_sec=0.1)
    finding = diagnose(result).findings[0]
    assert "UNKNOWN_RULE" in finding.title
    assert "future rule" in finding.explanation


# ---------------------------------------------------------------------------
# SKIPPED / ERRORED projection — keeps the UI coherent
# ---------------------------------------------------------------------------
def test_skipped_record_produces_unanalyzable_diagnosis(mono_wav: Path) -> None:
    result = scan_one(mono_wav, Config().with_overrides(workers=1))
    d = diagnose(result)
    assert d.is_analyzable is False
    assert d.headline.startswith("ℹ")
    assert "対象外" in d.headline or "対象外" in d.summary
    assert d.findings == ()


def test_errored_record_produces_failure_diagnosis() -> None:
    meta = FileMeta(
        file_path=Path("/tmp/x.wav"),
        sample_rate=0,
        duration_sec=0.0,
        channel_layout="unknown",
    )
    record = MetricRecord(
        meta=meta, status=ScanStatus.ERRORED, skip_reason="ValueError: bad header"
    )
    result = FileResult(record=record, flags=(), verdict=Verdict.OK, elapsed_sec=0.0)
    d = diagnose(result)
    assert d.is_analyzable is False
    assert d.headline.startswith("✗")
    assert "ValueError" in d.summary


def test_skipped_record_with_no_reason_falls_back_to_default_label() -> None:
    # Covers the ``record.skip_reason or "詳細不明"`` fallback when the
    # reason string is missing entirely.
    meta = FileMeta(
        file_path=Path("/tmp/x.wav"),
        sample_rate=48000,
        duration_sec=1.0,
        channel_layout="stereo",
    )
    record = MetricRecord(meta=meta, status=ScanStatus.SKIPPED, skip_reason=None)
    result = FileResult(record=record, flags=(), verdict=Verdict.OK, elapsed_sec=0.0)
    d = diagnose(result)
    assert d.is_analyzable is False
    assert "詳細不明" in d.summary


# ---------------------------------------------------------------------------
# Internal helpers — branch coverage for the _fmt_lu non-finite path
# ---------------------------------------------------------------------------
def test_fmt_lu_handles_nan_and_inf() -> None:
    from asmr_balance.web.views.diagnosis import _fmt_lu

    assert _fmt_lu(float("nan")) == "—"
    assert _fmt_lu(float("inf")) == "—"
    assert _fmt_lu(float("-inf")) == "—"
    assert _fmt_lu(3.5) == "+3.50 LU"
    assert _fmt_lu(-1.25) == "-1.25 LU"


# ---------------------------------------------------------------------------
# actions dedup
# ---------------------------------------------------------------------------
def test_actions_dedup_recommendations(panned_wav: Path) -> None:
    result = scan_one(panned_wav, Config().with_overrides(workers=1))
    d = diagnose(result)
    assert len(d.actions) == len(set(d.actions))
    # When findings exist, actions are non-empty.
    if d.findings:
        assert d.actions


# ---------------------------------------------------------------------------
# Diagnosis / Finding are frozen dataclasses (immutable wire shape)
# ---------------------------------------------------------------------------
def test_diagnosis_is_frozen() -> None:
    import dataclasses

    d = Diagnosis(
        verdict=Verdict.OK,
        headline="ok",
        summary="",
        findings=(),
        actions=(),
        is_analyzable=True,
    )
    with __import__("pytest").raises(dataclasses.FrozenInstanceError):
        d.headline = "boom"  # pyright: ignore[reportAttributeAccessIssue]


def test_finding_is_frozen() -> None:
    import dataclasses

    f = Finding(
        title="t",
        severity=Verdict.OK,
        explanation="e",
        recommendation="r",
        technical_ref="x",
    )
    with __import__("pytest").raises(dataclasses.FrozenInstanceError):
        f.title = "boom"  # pyright: ignore[reportAttributeAccessIssue]
