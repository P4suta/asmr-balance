"""Tests for :mod:`asmr_balance.scan.pipeline`."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import soundfile as sf

from asmr_balance.algebra.semilattice import Verdict
from asmr_balance.config.model import Config
from asmr_balance.metrics.record import ScanStatus
from asmr_balance.scan.pipeline import scan_one
from asmr_balance.source.adt import LayoutPolicy


def _write_stereo_wav(
    path: Path, sample_rate: int = 48000, n_seconds: float = 0.5, pan_db: float = 0.0
) -> Path:
    rng = np.random.default_rng(seed=0)
    n_samples = int(sample_rate * n_seconds)
    sig = rng.standard_normal(n_samples).astype(np.float32) * 0.1
    pan_factor = 10 ** (-abs(pan_db) / 20.0)
    if pan_db >= 0:
        stereo = np.column_stack([sig, sig * pan_factor])
    else:
        stereo = np.column_stack([sig * pan_factor, sig])
    sf.write(str(path), stereo, sample_rate, subtype="FLOAT")
    return path


def test_scan_one_balanced_yields_ok(tmp_path: Path) -> None:
    p = _write_stereo_wav(tmp_path / "balanced.wav")
    result = scan_one(p, Config())
    assert result.record.status is ScanStatus.ANALYZED
    # Random noise of equal amplitude is balanced (delta_lu near 0).
    assert result.record.loudness is not None
    assert abs(result.record.loudness.delta_lu) < 1.0


def test_scan_one_panned_triggers_lr_balance_fail(tmp_path: Path) -> None:
    p = _write_stereo_wav(tmp_path / "panned.wav", pan_db=20.0)
    result = scan_one(p, Config())
    codes = {f.code for f in result.flags}
    assert "LR_BALANCE_FAIL" in codes
    assert result.verdict is Verdict.FAIL


def test_scan_one_mono_is_skipped(tmp_path: Path) -> None:
    p = tmp_path / "mono.wav"
    sig = np.zeros((4800, 1), dtype=np.float32)
    sf.write(str(p), sig, 48000, subtype="FLOAT")
    result = scan_one(p, Config())
    assert result.record.status is ScanStatus.SKIPPED
    assert result.record.skip_reason is not None
    assert "mono" in result.record.skip_reason
    assert result.flags == ()
    assert result.verdict is Verdict.OK


def test_scan_one_records_elapsed_time(tmp_path: Path) -> None:
    p = _write_stereo_wav(tmp_path / "x.wav", n_seconds=0.1)
    result = scan_one(p, Config())
    assert result.elapsed_sec > 0.0


def test_scan_one_unsupported_extension_is_errored(tmp_path: Path) -> None:
    p = tmp_path / "x.bogus"
    p.write_bytes(b"\x00" * 100)
    result = scan_one(p, Config())
    assert result.record.status is ScanStatus.ERRORED
    assert result.record.skip_reason is not None


def test_scan_one_emits_progress_stages_in_order(tmp_path: Path) -> None:
    """Every stage boundary fires; ``analyze`` may tick many times, ``complete`` is last."""
    p = _write_stereo_wav(tmp_path / "x.wav", n_seconds=0.5)
    events: list[tuple[str, int, int]] = []
    result = scan_one(p, Config(), on_progress=lambda s, c, t: events.append((s, c, t)))
    assert result.record.status is ScanStatus.ANALYZED

    stages = [s for s, _, _ in events]
    # Required boundaries on the happy path.
    for required in ("probe", "decode", "analyze", "assemble", "evaluate", "complete"):
        assert required in stages, f"missing stage {required} in {stages}"
    # Probe-start fires before probe-done, etc.
    assert stages.index("probe") < stages.index("decode") < stages.index("analyze")
    assert stages.index("analyze") < stages.index("assemble") < stages.index("evaluate")
    assert stages[-1] == "complete"


def test_scan_one_emits_skipped_stage_for_mono(tmp_path: Path) -> None:
    p = tmp_path / "mono.wav"
    sig = np.zeros((4800, 1), dtype=np.float32)
    sf.write(str(p), sig, 48000, subtype="FLOAT")
    events: list[str] = []
    scan_one(p, Config(), on_progress=lambda s, _c, _t: events.append(s))
    assert "skipped" in events
    # No analyze / evaluate on skipped files.
    assert "analyze" not in events
    assert "evaluate" not in events
    assert events[-1] == "complete"


def test_scan_one_progress_callback_optional(tmp_path: Path) -> None:
    """The default (no callback) path stays callable and produces identical results."""
    p = _write_stereo_wav(tmp_path / "x.wav", n_seconds=0.2)
    a = scan_one(p, Config())
    b = scan_one(p, Config(), on_progress=None)
    assert a.record.status is b.record.status
    assert a.verdict is b.verdict


def test_scan_one_layout_skip_policy(tmp_path: Path) -> None:
    p = tmp_path / "surround.wav"
    rng = np.random.default_rng(seed=0)
    samples = (rng.standard_normal((4800, 6)) * 0.1).astype(np.float32)
    sf.write(str(p), samples, 48000, subtype="FLOAT")
    cfg = Config(layout_policy=LayoutPolicy.SKIP)
    result = scan_one(p, cfg)
    assert result.record.status is ScanStatus.SKIPPED
