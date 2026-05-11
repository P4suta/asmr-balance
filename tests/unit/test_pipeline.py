"""Tests for ``asmr_balance.pipeline``."""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
import soundfile as sf

from asmr_balance.config import Config, LayoutPolicy
from asmr_balance.pipeline import find_audio_files, scan_many, scan_one
from asmr_balance.types import Verdict

if TYPE_CHECKING:
    from pathlib import Path

SR = 48000


def _write_stereo(
    path: Path,
    *,
    duration: float = 1.0,
    amp_l: float = 0.3,
    amp_r: float = 0.3,
) -> None:
    n = int(duration * SR)
    t = np.arange(n, dtype=np.float64) / SR
    left = (amp_l * np.sin(2.0 * np.pi * 1000.0 * t)).astype(np.float32)
    right = (amp_r * np.sin(2.0 * np.pi * 1000.0 * t)).astype(np.float32)
    sf.write(str(path), np.column_stack([left, right]).astype(np.float32), SR)


def test_find_audio_files_single_file(tmp_path: Path) -> None:
    path = tmp_path / "a.wav"
    path.write_bytes(b"")
    assert find_audio_files(path) == [path]


def test_find_audio_files_directory_filters_extensions(tmp_path: Path) -> None:
    (tmp_path / "a.wav").write_bytes(b"")
    (tmp_path / "b.txt").write_bytes(b"")
    (tmp_path / "nested").mkdir()
    (tmp_path / "nested" / "c.flac").write_bytes(b"")
    files = find_audio_files(tmp_path)
    suffixes = sorted(p.suffix for p in files)
    assert suffixes == [".flac", ".wav"]


def test_scan_one_returns_metric_record_for_stereo(tmp_path: Path) -> None:
    path = tmp_path / "stereo.wav"
    _write_stereo(path, duration=1.0)
    result = scan_one(path, Config())
    assert result.metrics.skipped is False
    # L == R for a pure tone → Pearson r ≈ 1.0 fires PSEUDO_MONO (WARN), no FAIL
    assert result.verdict is not Verdict.FAIL


def test_scan_one_skips_mono(tmp_path: Path) -> None:
    path = tmp_path / "mono.wav"
    n = SR
    sf.write(str(path), np.zeros(n, dtype=np.float32), SR)
    result = scan_one(path, Config())
    assert result.metrics.skipped is True
    assert result.metrics.skip_reason is not None
    assert "mono" in result.metrics.skip_reason


def test_scan_one_panned_signal_flags_fail(tmp_path: Path) -> None:
    path = tmp_path / "panned.wav"
    _write_stereo(path, duration=2.0, amp_l=0.5, amp_r=0.5 / 4.0)  # 12 dB
    result = scan_one(path, Config())
    codes = {f.code for f in result.flags}
    assert "LR_BALANCE_FAIL" in codes
    assert result.verdict is Verdict.FAIL


def test_scan_many_handles_error_files(tmp_path: Path) -> None:
    good = tmp_path / "good.wav"
    _write_stereo(good)
    bad = tmp_path / "bad.wav"
    bad.write_bytes(b"not a wav")
    results = scan_many([good, bad], Config())
    assert len(results) == 2
    statuses = [r.verdict for r in results]
    assert Verdict.FAIL in statuses


def test_scan_one_respects_skip_layout_policy_for_multichannel(tmp_path: Path) -> None:
    path = tmp_path / "5_1.wav"
    n = SR // 4
    sf.write(str(path), np.zeros((n, 6), dtype=np.float32), SR)
    cfg = Config(layout_policy=LayoutPolicy.SKIP)
    result = scan_one(path, cfg)
    assert result.metrics.skipped is True
    assert "6 channels" in (result.metrics.skip_reason or "")
