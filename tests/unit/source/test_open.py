"""Tests for :func:`asmr_balance.source.open.open_source`."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from asmr_balance.source import (
    LayoutPolicy,
    SkipLayout,
    SkipMono,
    Source,
    iter_blocks,
    open_source,
)


def _write_wav(path: Path, channels: int, n_frames: int = 4800, sample_rate: int = 48000) -> Path:
    """Write a synthetic ``channels``-channel float32 WAV at ``path``."""
    arr = np.tile(
        np.arange(n_frames, dtype=np.float32).reshape(-1, 1) * 1e-3,
        (1, channels),
    )
    sf.write(str(path), arr, samplerate=sample_rate, subtype="FLOAT")
    return path


def test_open_stereo_returns_source(tmp_path: Path) -> None:
    p = _write_wav(tmp_path / "stereo.wav", channels=2)
    result = open_source(p, LayoutPolicy.DOWNMIX, block_samples=4800)
    assert isinstance(result, Source)
    assert result.n_channels == 2
    assert result.meta.sample_rate == 48000
    assert result.block_samples == 4800
    assert result.meta.channel_layout == "stereo"


def test_open_mono_returns_skip_mono(tmp_path: Path) -> None:
    p = _write_wav(tmp_path / "mono.wav", channels=1)
    result = open_source(p, LayoutPolicy.DOWNMIX, block_samples=4800)
    assert isinstance(result, SkipMono)
    assert result.meta.channel_layout == "mono"


def test_open_5_1_with_skip_policy_returns_skip_layout(tmp_path: Path) -> None:
    p = _write_wav(tmp_path / "surround.wav", channels=6)
    result = open_source(p, LayoutPolicy.SKIP, block_samples=4800)
    assert isinstance(result, SkipLayout)
    assert result.n_channels == 6


def test_open_5_1_with_downmix_returns_source(tmp_path: Path) -> None:
    p = _write_wav(tmp_path / "surround.wav", channels=6)
    result = open_source(p, LayoutPolicy.DOWNMIX, block_samples=4800)
    assert isinstance(result, Source)
    assert result.n_channels == 6
    assert result.meta.channel_layout == "5.1"


def test_open_invalid_block_samples_raises(tmp_path: Path) -> None:
    p = _write_wav(tmp_path / "s.wav", channels=2)
    with pytest.raises(ValueError, match="block_samples"):
        open_source(p, LayoutPolicy.DOWNMIX, block_samples=0)


def test_iter_blocks_yields_correctly_shaped_blocks(tmp_path: Path) -> None:
    p = _write_wav(tmp_path / "stereo.wav", channels=2, n_frames=10000)
    src = open_source(p, LayoutPolicy.DOWNMIX, block_samples=4800)
    assert isinstance(src, Source)
    blocks = list(iter_blocks(src))
    # 10000 frames / 4800 per block = 2 full blocks + remainder of 400.
    assert len(blocks) >= 2
    for b in blocks[:-1]:
        assert b.shape == (4800, 2)
        assert b.dtype == np.float32
    assert blocks[-1].shape[0] <= 4800


def test_iter_blocks_5_1_yields_stereo(tmp_path: Path) -> None:
    p = _write_wav(tmp_path / "surround.wav", channels=6, n_frames=4800)
    src = open_source(p, LayoutPolicy.DOWNMIX, block_samples=4800)
    assert isinstance(src, Source)
    blocks = list(iter_blocks(src))
    assert all(b.shape[1] == 2 for b in blocks)


def test_unsupported_extension_raises(tmp_path: Path) -> None:
    p = tmp_path / "data.bogus"
    p.write_bytes(b"\x00" * 100)
    with pytest.raises(ValueError, match="unsupported"):
        open_source(p, LayoutPolicy.DOWNMIX, block_samples=4800)


def test_skip_results_carry_meta(tmp_path: Path) -> None:
    """SkipMono / SkipLayout still expose meta so the pipeline can log file info."""
    p = _write_wav(tmp_path / "m.wav", channels=1)
    result = open_source(p, LayoutPolicy.DOWNMIX, block_samples=4800)
    assert isinstance(result, SkipMono)
    assert result.meta.file_path == p
    assert result.meta.sample_rate == 48000
