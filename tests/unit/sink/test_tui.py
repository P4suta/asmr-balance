"""Tests for :mod:`asmr_balance.sink.tui`."""

from __future__ import annotations

import io
from pathlib import Path

import numpy as np
import soundfile as sf
from rich.console import Console

from asmr_balance.config.model import Config
from asmr_balance.scan.pipeline import scan_one
from asmr_balance.sink.tui import (
    InspectRenderer,
    TuiSummarySink,
    render_inspect,
    render_summary,
)


def _stereo_wav(path: Path) -> Path:
    rng = np.random.default_rng(seed=0)
    samples = (rng.standard_normal((4800, 2)) * 0.1).astype(np.float32)
    sf.write(str(path), samples, 48000, subtype="FLOAT")
    return path


def _io_console() -> tuple[Console, io.StringIO]:
    """Plain-text console + the buffer behind it, so tests can read output.

    Returning the buffer alongside the Console sidesteps the typeshed
    ``IO[str]`` stub gap (no ``.getvalue``) without per-call casts.
    """
    buf = io.StringIO()
    return Console(file=buf, width=200, force_terminal=False, color_system=None), buf


def test_render_summary_emits_table(tmp_path: Path) -> None:
    src = _stereo_wav(tmp_path / "a.wav")
    result = scan_one(src, Config())
    console, buf = _io_console()
    render_summary([result], console=console)
    output = buf.getvalue()
    assert "a.wav" in output
    assert "Pearson" in output


def test_render_inspect_analyzed_file(tmp_path: Path) -> None:
    src = _stereo_wav(tmp_path / "x.wav")
    result = scan_one(src, Config())
    console, buf = _io_console()
    render_inspect(result, console=console)
    output = buf.getvalue()
    assert "x.wav" in output
    assert "loudness.lufs_i_stereo" in output


def test_render_inspect_skipped_file(tmp_path: Path) -> None:
    # Mono is skipped.
    p = tmp_path / "mono.wav"
    sf.write(str(p), np.zeros((4800, 1), dtype=np.float32), 48000, subtype="FLOAT")
    result = scan_one(p, Config())
    console, buf = _io_console()
    render_inspect(result, console=console)
    output = buf.getvalue()
    assert "skipped" in output
    assert "mono" in output


def test_tui_summary_sink_writes_results(tmp_path: Path) -> None:
    src = _stereo_wav(tmp_path / "a.wav")
    result = scan_one(src, Config())
    console, buf = _io_console()
    sink = TuiSummarySink(console=console)
    sink.open()
    sink.write(result)
    sink.close()
    output = buf.getvalue()
    assert "a.wav" in output


def test_inspect_renderer_class() -> None:
    """Smoke test the class wrapper."""
    console, _buf = _io_console()
    r = InspectRenderer(console=console)
    assert r.console is not None
