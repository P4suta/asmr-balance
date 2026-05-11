"""Tests for ``asmr_balance.report.html``."""

from __future__ import annotations

import math
from pathlib import Path

from asmr_balance.report.html import _fmt, write_html
from asmr_balance.types import FileResult, Flag, MetricRecord, Verdict


def _make_result(
    *,
    file_path: Path = Path("/tmp/x.wav"),
    delta_lu: float = 1.0,
    verdict: Verdict = Verdict.OK,
    flags: tuple[Flag, ...] = (),
) -> FileResult:
    metrics = MetricRecord(
        file_path=file_path,
        sample_rate=48000,
        duration_sec=1.0,
        channel_layout="stereo",
        delta_lu=delta_lu,
    )
    return FileResult(metrics=metrics, flags=flags, verdict=verdict)


def test_fmt_handles_nan_inf_finite() -> None:
    assert _fmt(math.nan) == "—"
    assert _fmt(float("inf")) == "+∞"
    assert _fmt(float("-inf")) == "−∞"
    assert _fmt(1.23, fmt=".2f", unit=" LU") == "1.23 LU"


def test_write_html_creates_report_with_rows(tmp_path: Path) -> None:
    fail_flag = Flag(code="LR_BALANCE_FAIL", severity=Verdict.FAIL, message="x")
    results = [
        _make_result(file_path=tmp_path / "a.wav", verdict=Verdict.OK),
        _make_result(
            file_path=tmp_path / "b.wav",
            verdict=Verdict.FAIL,
            delta_lu=12.5,
            flags=(fail_flag,),
        ),
    ]
    out = tmp_path / "report.html"
    rows = write_html(results, out)
    assert rows == 2
    body = out.read_text(encoding="utf-8")
    assert "a.wav" in body
    assert "b.wav" in body
    assert "LR_BALANCE_FAIL" in body
    assert "Plotly" in body  # CDN script tag
    assert "<bar" not in body  # quick sanity (no obvious template bug)


def test_write_html_handles_no_finite_deltas(tmp_path: Path) -> None:
    """When every file is silent (delta_lu == nan), no bars are plotted."""
    result = _make_result(file_path=tmp_path / "silent.wav", delta_lu=math.nan)
    out = tmp_path / "report.html"
    rows = write_html([result], out)
    assert rows == 1
    body = out.read_text(encoding="utf-8")
    assert '"x": []' in body or '"x":[]' in body  # empty x array in chart


def test_write_html_escapes_special_chars_in_filename(tmp_path: Path) -> None:
    weird = tmp_path / "<weird>.wav"
    weird.write_bytes(b"")
    result = _make_result(file_path=weird)
    out = tmp_path / "report.html"
    write_html([result], out)
    body = out.read_text(encoding="utf-8")
    assert "&lt;weird&gt;.wav" in body
    assert "<weird>.wav" not in body  # raw form must be escaped
