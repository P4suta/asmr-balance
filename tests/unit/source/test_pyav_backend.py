"""Tests for the PyAV backend — exercises MP3 round-trip via system ffmpeg.

These tests are skipped if ``ffmpeg`` is not available, but the project's
Docker image installs it (see ``Dockerfile``), so they run in CI.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from asmr_balance.config.model import Config
from asmr_balance.metrics.record import ScanStatus
from asmr_balance.scan.pipeline import scan_one
from asmr_balance.source.adt import LayoutPolicy
from asmr_balance.source.open import iter_blocks, open_source
from tests.fixtures.gen_fixtures import reencode_wav_to

pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg missing")


def _make_mp3_fixture(tmp_path: Path) -> Path:
    wav = tmp_path / "src.wav"
    sr = 48000
    rng = np.random.default_rng(seed=0)
    samples = (rng.standard_normal((sr // 2, 2)) * 0.1).astype(np.float32)
    sf.write(str(wav), samples, sr, subtype="FLOAT")
    mp3 = tmp_path / "src.mp3"
    reencode_wav_to(wav, mp3)
    return mp3


def test_open_source_for_mp3(tmp_path: Path) -> None:
    mp3 = _make_mp3_fixture(tmp_path)
    src = open_source(mp3, LayoutPolicy.DOWNMIX, block_samples=4800)
    from asmr_balance.source.adt import Source

    assert isinstance(src, Source)
    assert src.meta.sample_rate == 48000


def test_iter_blocks_mp3_yields_stereo_blocks(tmp_path: Path) -> None:
    mp3 = _make_mp3_fixture(tmp_path)
    src = open_source(mp3, LayoutPolicy.DOWNMIX, block_samples=4800)
    from asmr_balance.source.adt import Source

    assert isinstance(src, Source)
    blocks = list(iter_blocks(src))
    assert blocks
    assert all(b.shape[1] == 2 for b in blocks)
    assert all(b.dtype == np.float32 for b in blocks)


def test_scan_one_mp3_produces_metrics(tmp_path: Path) -> None:
    mp3 = _make_mp3_fixture(tmp_path)
    result = scan_one(mp3, Config())
    assert result.record.status is ScanStatus.ANALYZED
    assert result.record.loudness is not None


def test_pyav_probe_fails_for_audio_less_container(tmp_path: Path) -> None:
    """An MP4 with no audio stream raises ValueError("no audio stream")."""
    # Create a 1-frame silent MP4 with only a video stream.
    import subprocess

    out = tmp_path / "silent.mp4"
    cmd = [
        "ffmpeg",
        "-y",
        "-f",
        "lavfi",
        "-i",
        "color=c=black:s=64x64:d=0.5",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-an",
        str(out),
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    result = scan_one(out, Config())
    assert result.record.status is ScanStatus.ERRORED
    assert "no audio stream" in (result.record.skip_reason or "")
