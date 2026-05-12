"""Tests for :class:`asmr_balance.sink.html.HtmlSink`."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import soundfile as sf

from asmr_balance.config.model import Config
from asmr_balance.scan.pipeline import scan_one
from asmr_balance.sink.html import HtmlSink


def _stereo_wav(path: Path) -> Path:
    rng = np.random.default_rng(seed=0)
    samples = (rng.standard_normal((4800, 2)) * 0.1).astype(np.float32)
    sf.write(str(path), samples, 48000, subtype="FLOAT")
    return path


def test_html_sink_writes_html_file(tmp_path: Path) -> None:
    src = _stereo_wav(tmp_path / "a.wav")
    out = tmp_path / "report.html"
    sink = HtmlSink(path=out)
    sink.open()
    sink.write(scan_one(src, Config()))
    sink.close()
    text = out.read_text(encoding="utf-8")
    assert "<!doctype html>" in text
    assert "asmr-balance report" in text
    assert "a.wav" in text
    assert "plotly" in text.lower()


def test_html_sink_shows_summary_counts(tmp_path: Path) -> None:
    src = _stereo_wav(tmp_path / "a.wav")
    out = tmp_path / "r.html"
    sink = HtmlSink(path=out)
    sink.open()
    sink.write(scan_one(src, Config()))
    sink.close()
    text = out.read_text(encoding="utf-8")
    assert "OK:" in text
    assert "WARN:" in text
    assert "FAIL:" in text
