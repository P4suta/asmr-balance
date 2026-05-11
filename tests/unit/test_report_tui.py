"""Tests for ``asmr_balance.report.tui``."""

from __future__ import annotations

import math
from pathlib import Path

from rich.console import Console

from asmr_balance.report.tui import _fmt, render_inspect, render_summary
from asmr_balance.types import FileResult, Flag, MetricRecord, Verdict


def _make_result(
    *,
    file_path: Path = Path("/tmp/x.wav"),
    delta_lu: float = 1.0,
    verdict: Verdict = Verdict.OK,
    flags: tuple[Flag, ...] = (),
    pearson_r: float = 0.5,
    low_phase_coherence: float = 0.5,
) -> FileResult:
    metrics = MetricRecord(
        file_path=file_path,
        sample_rate=48000,
        duration_sec=1.0,
        channel_layout="stereo",
        delta_lu=delta_lu,
        pearson_r=pearson_r,
        low_phase_coherence=low_phase_coherence,
    )
    return FileResult(metrics=metrics, flags=flags, verdict=verdict)


def test_fmt_finite_value() -> None:
    assert _fmt(1.234, fmt=".2f", unit=" LU") == "1.23 LU"


def test_fmt_nan() -> None:
    assert _fmt(math.nan) == "—"


def test_fmt_negative_inf() -> None:
    assert _fmt(float("-inf")) == "−∞"


def test_fmt_positive_inf() -> None:
    assert _fmt(float("inf")) == "+∞"


def test_render_summary_includes_filename_and_verdict() -> None:
    out = Console(record=True, force_terminal=False, color_system=None, width=200)
    fail_flag = Flag(code="LR_BALANCE_FAIL", severity=Verdict.FAIL, message="x")
    results = [
        _make_result(file_path=Path("/tmp/a.wav"), verdict=Verdict.OK),
        _make_result(
            file_path=Path("/tmp/b.wav"),
            verdict=Verdict.FAIL,
            delta_lu=12.0,
            flags=(fail_flag,),
        ),
    ]
    render_summary(results, out)
    text = out.export_text()
    assert "a.wav" in text
    assert "b.wav" in text
    assert "LR_BALANCE_FAIL" in text
    assert "Total: 2 files" in text


def test_render_inspect_emits_panel_and_tables() -> None:
    out = Console(record=True, force_terminal=False, color_system=None, width=200)
    result = _make_result(
        verdict=Verdict.WARN,
        flags=(Flag(code="PSEUDO_MONO", severity=Verdict.WARN, message="r=0.97"),),
    )
    render_inspect(result, out)
    text = out.export_text()
    assert "asmr-balance inspect" in text
    assert "WARN" in text
    assert "PSEUDO_MONO" in text


def test_render_inspect_without_flags_omits_flag_table() -> None:
    out = Console(record=True, force_terminal=False, color_system=None, width=200)
    result = _make_result(verdict=Verdict.OK)
    render_inspect(result, out)
    text = out.export_text()
    assert "Flags" not in text  # no flag-table title rendered


def test_render_summary_handles_empty_input() -> None:
    out = Console(record=True, force_terminal=False, color_system=None, width=200)
    render_summary([], out)
    text = out.export_text()
    assert "Total: 0 files" in text
