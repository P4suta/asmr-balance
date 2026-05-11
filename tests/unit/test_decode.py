"""Tests for ``asmr_balance.decode``."""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
import pytest
import soundfile as sf

from asmr_balance.decode import iter_pcm_blocks, probe
from tests.fixtures.gen_fixtures import reencode_wav_to, write_balanced_tone, write_panned_tone

if TYPE_CHECKING:
    from pathlib import Path

SR = 48000


@pytest.fixture
def stereo_wav(tmp_path: Path) -> Path:
    path = tmp_path / "stereo.wav"
    data = np.zeros((SR, 2), dtype=np.float32)
    sf.write(str(path), data, SR)
    return path


@pytest.fixture
def mono_wav(tmp_path: Path) -> Path:
    path = tmp_path / "mono.wav"
    data = np.zeros(SR, dtype=np.float32)
    sf.write(str(path), data, SR)
    return path


def test_probe_stereo(stereo_wav: Path) -> None:
    m = probe(stereo_wav)
    assert m.n_channels == 2
    assert m.sample_rate == SR
    assert m.layout_name == "stereo"
    assert m.duration_sec == pytest.approx(1.0)


def test_probe_mono(mono_wav: Path) -> None:
    m = probe(mono_wav)
    assert m.n_channels == 1
    assert m.layout_name == "mono"


def test_probe_high_channel_count_uses_numeric_fallback(tmp_path: Path) -> None:
    path = tmp_path / "10ch.wav"
    data = np.zeros((SR, 10), dtype=np.float32)
    sf.write(str(path), data, SR)
    m = probe(path)
    assert m.layout_name == "10ch"


def test_iter_blocks_rejects_zero_block_samples(stereo_wav: Path) -> None:
    m = probe(stereo_wav)
    with pytest.raises(ValueError, match="positive"):
        next(iter_pcm_blocks(m, block_samples=0))


def test_iter_blocks_yields_blocks_in_correct_shape(stereo_wav: Path) -> None:
    m = probe(stereo_wav)
    blocks = list(iter_pcm_blocks(m, block_samples=4800))
    assert blocks
    for block in blocks:
        assert block.ndim == 2
        assert block.shape[1] == 2
        assert block.dtype == np.float32


def test_iter_blocks_total_equals_frames(stereo_wav: Path) -> None:
    m = probe(stereo_wav)
    blocks = list(iter_pcm_blocks(m, block_samples=10000))
    total = sum(b.shape[0] for b in blocks)
    assert total == m.n_frames


# --- PyAV path -------------------------------------------------------------


@pytest.fixture
def mp4_balanced(tmp_path: Path) -> Path:
    src = tmp_path / "src.wav"
    write_balanced_tone(src, duration_sec=1.5)
    target = tmp_path / "balanced.mp4"
    reencode_wav_to(src, target)
    return target


def test_probe_via_pyav_for_mp4(mp4_balanced: Path) -> None:
    m = probe(mp4_balanced)
    assert m.n_channels == 2
    assert m.layout_name == "stereo"
    assert m.sample_rate > 0
    assert m.duration_sec > 0.5


def test_iter_blocks_via_pyav_yields_stereo_blocks(mp4_balanced: Path) -> None:
    m = probe(mp4_balanced)
    blocks = list(iter_pcm_blocks(m, block_samples=4800))
    assert blocks
    for block in blocks:
        assert block.ndim == 2
        assert block.shape[1] == 2
        assert block.dtype == np.float32


def test_pyav_probe_rejects_audio_less_file(tmp_path: Path) -> None:
    # Create a valid video-only mp4 (no audio stream) and confirm we raise.
    out = tmp_path / "video_only.mp4"
    import subprocess  # noqa: PLC0415

    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=size=320x240:rate=5:color=black",
            "-t",
            "0.5",
            "-an",
            str(out),
        ],
        check=True,
        capture_output=True,
    )
    with pytest.raises(ValueError, match="No audio"):
        probe(out)


def test_pyav_iter_panned_signal_yields_data(tmp_path: Path) -> None:
    wav = tmp_path / "panned.wav"
    write_panned_tone(wav, duration_sec=1.0)
    mp4 = tmp_path / "panned.mp4"
    reencode_wav_to(wav, mp4)
    m = probe(mp4)
    blocks = list(iter_pcm_blocks(m, block_samples=2400))
    # We should have at least a few thousand samples decoded
    total = sum(b.shape[0] for b in blocks)
    assert total > SR // 2
