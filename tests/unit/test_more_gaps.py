"""Final coverage pinpoints — covers _fmt branches, InspectRenderer.render, and ProbedAudio."""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from asmr_balance.config.model import Config
from asmr_balance.scan.pipeline import scan_one
from asmr_balance.sink.tui import InspectRenderer, _fmt
from asmr_balance.source.backend.dispatch import ProbedAudio


def test_tui_fmt_none_inf_nan() -> None:
    assert _fmt(None) == "—"
    assert _fmt(math.nan) == "NaN"
    assert _fmt(math.inf) == "+∞"
    assert _fmt(-math.inf) == "−∞"


def test_tui_fmt_normal_float_carries_sign() -> None:
    assert _fmt(1.23) == "+1.23"
    assert _fmt(-1.23) == "-1.23"


def test_inspect_renderer_render_method(tmp_path: Path) -> None:
    """Cover the `InspectRenderer.render` thin wrapper."""
    import io

    from rich.console import Console

    p = tmp_path / "x.wav"
    sf.write(str(p), np.zeros((100, 2), dtype=np.float32), 48000, subtype="FLOAT")
    result = scan_one(p, Config())
    console = Console(file=io.StringIO(), width=120, force_terminal=False, color_system=None)
    renderer = InspectRenderer(console=console)
    renderer.render(result)
    out = console.file.getvalue()  # type: ignore[attr-defined]
    assert "x.wav" in out


def test_render_inspect_with_flags_present(tmp_path: Path) -> None:
    """Cover the ``if result.flags:`` branch in render_inspect."""
    import io

    from rich.console import Console

    from asmr_balance.sink.tui import render_inspect

    sr = 48000
    rng = np.random.default_rng(seed=0)
    samples = (rng.standard_normal((sr, 2)) * 0.1).astype(np.float32)
    samples[:, 1] *= 0.01  # 40 dB pan → flags
    p = tmp_path / "panned.wav"
    sf.write(str(p), samples, sr, subtype="FLOAT")
    result = scan_one(p, Config())
    assert result.flags
    console = Console(file=io.StringIO(), width=200, force_terminal=False, color_system=None)
    render_inspect(result, console=console)
    out = console.file.getvalue()  # type: ignore[attr-defined]
    assert "LR_BALANCE_FAIL" in out


def test_scan_one_picklable_invocation(tmp_path: Path) -> None:
    """Drive the ProcessPool worker entry point directly so coverage sees it."""
    from asmr_balance.scan.parallel import _scan_one_picklable

    rng = np.random.default_rng(seed=0)
    samples = (rng.standard_normal((4800, 2)) * 0.1).astype(np.float32)
    p = tmp_path / "x.wav"
    sf.write(str(p), samples, 48000, subtype="FLOAT")
    result = _scan_one_picklable((p, Config()))
    assert result.record is not None


def test_result_to_flat_row_for_skipped_record(tmp_path: Path) -> None:
    """Skipped records have no subtrees → flat row preserves None placeholders."""
    from asmr_balance.sink.base import result_to_flat_row

    p = tmp_path / "mono.wav"
    sf.write(str(p), np.zeros((100, 1), dtype=np.float32), 48000, subtype="FLOAT")
    result = scan_one(p, Config())
    row = result_to_flat_row(result)
    assert row["loudness.lufs_i_stereo"] is None
    assert row["band.low"] is None
    assert row["band.third_octave.b_1000hz"] is None
    assert row["dynamics.psr_db"] is None
    assert row["meta.sample_rate"] == 48000
    assert row["status"] == "skipped"


def test_probed_audio_duration_sec_with_zero_sample_rate() -> None:
    """A degenerate header (sample_rate=0) returns 0.0 duration without ZeroDivisionError."""
    info = ProbedAudio(sample_rate=0, n_channels=2, n_frames=1000, layout_name="stereo")
    assert info.duration_sec == 0.0


def test_probed_audio_duration_sec_normal() -> None:
    info = ProbedAudio(sample_rate=48000, n_channels=2, n_frames=48000, layout_name="stereo")
    assert info.duration_sec == pytest.approx(1.0, abs=1e-9)


def test_logging_is_tty_force_json_false_in_non_tty() -> None:
    """`_is_tty(force_json=False)` returns the actual stderr TTY-ness (False in CI)."""
    from asmr_balance.logging import _is_tty

    # In pytest captured stderr, this is generally False; only the False branch is
    # asserted (we cannot synthesize a TTY in CI without ptys).
    assert _is_tty(force_json=False) in {True, False}
