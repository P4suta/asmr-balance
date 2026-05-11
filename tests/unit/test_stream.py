"""Tests for ``asmr_balance.stream``."""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
import soundfile as sf

from asmr_balance.config import LayoutPolicy
from asmr_balance.decode import probe
from asmr_balance.stream import (
    iter_stereo_blocks,
    should_skip,
    skip_reason,
    to_stereo,
)

if TYPE_CHECKING:
    from pathlib import Path

SR = 48000


def test_to_stereo_mono_returns_none() -> None:
    frame = np.zeros((1024, 1), dtype=np.float32)
    assert to_stereo(frame, n_channels=1, policy=LayoutPolicy.DOWNMIX) is None


def test_to_stereo_stereo_passes_through() -> None:
    frame = np.ones((1024, 2), dtype=np.float32) * 0.3
    out = to_stereo(frame, n_channels=2, policy=LayoutPolicy.DOWNMIX)
    assert out is not None
    assert out.shape == (1024, 2)
    np.testing.assert_allclose(out, frame)


def test_to_stereo_skip_policy_for_multichannel() -> None:
    frame = np.zeros((1024, 6), dtype=np.float32)
    assert to_stereo(frame, n_channels=6, policy=LayoutPolicy.SKIP) is None


def test_to_stereo_fl_fr_policy() -> None:
    frame = np.tile(np.arange(6, dtype=np.float32), (10, 1))
    out = to_stereo(frame, n_channels=6, policy=LayoutPolicy.FL_FR)
    assert out is not None
    assert out.shape == (10, 2)
    np.testing.assert_allclose(out[:, 0], 0.0)
    np.testing.assert_allclose(out[:, 1], 1.0)


def test_to_stereo_4ch_falls_back_to_fl_fr() -> None:
    frame = np.tile(np.arange(4, dtype=np.float32), (10, 1))
    out = to_stereo(frame, n_channels=4, policy=LayoutPolicy.DOWNMIX)
    assert out is not None
    np.testing.assert_allclose(out[:, 0], 0.0)
    np.testing.assert_allclose(out[:, 1], 1.0)


def test_to_stereo_5_1_downmix_adds_centre_and_back() -> None:
    fl = np.full(10, 1.0, dtype=np.float32)
    fr = np.full(10, 1.0, dtype=np.float32)
    fc = np.full(10, 1.0, dtype=np.float32)
    lfe = np.zeros(10, dtype=np.float32)
    bl = np.full(10, 1.0, dtype=np.float32)
    br = np.full(10, 1.0, dtype=np.float32)
    frame = np.column_stack([fl, fr, fc, lfe, bl, br]).astype(np.float32)
    out = to_stereo(frame, n_channels=6, policy=LayoutPolicy.DOWNMIX)
    assert out is not None
    expected_left = 1.0 + (1.0 / np.sqrt(2.0)) + 0.5
    np.testing.assert_allclose(out[:, 0], expected_left, atol=1e-6)


def test_to_stereo_5_channels_uses_zero_back_right() -> None:
    fl = np.full(10, 1.0, dtype=np.float32)
    fr = np.full(10, 1.0, dtype=np.float32)
    fc = np.full(10, 1.0, dtype=np.float32)
    lfe = np.zeros(10, dtype=np.float32)
    bl = np.full(10, 1.0, dtype=np.float32)
    frame = np.column_stack([fl, fr, fc, lfe, bl]).astype(np.float32)
    out = to_stereo(frame, n_channels=5, policy=LayoutPolicy.DOWNMIX)
    assert out is not None
    expected_left = 1.0 + (1.0 / np.sqrt(2.0)) + 0.5
    expected_right = 1.0 + (1.0 / np.sqrt(2.0))  # br is missing → 0
    np.testing.assert_allclose(out[:, 0], expected_left, atol=1e-6)
    np.testing.assert_allclose(out[:, 1], expected_right, atol=1e-6)


def test_should_skip_for_mono() -> None:
    assert should_skip(1, LayoutPolicy.DOWNMIX) is True


def test_should_skip_for_stereo() -> None:
    assert should_skip(2, LayoutPolicy.DOWNMIX) is False


def test_should_skip_for_multichannel_with_skip_policy() -> None:
    assert should_skip(6, LayoutPolicy.SKIP) is True


def test_should_skip_for_multichannel_with_downmix_policy() -> None:
    assert should_skip(6, LayoutPolicy.DOWNMIX) is False


def test_skip_reason_mono() -> None:
    assert "mono" in skip_reason(1, LayoutPolicy.DOWNMIX)


def test_skip_reason_multichannel_skip_policy() -> None:
    msg = skip_reason(6, LayoutPolicy.SKIP)
    assert "6 channels" in msg


def test_skip_reason_when_not_skipped_is_empty() -> None:
    assert skip_reason(2, LayoutPolicy.DOWNMIX) == ""


def test_iter_stereo_blocks_skipped_yields_nothing(tmp_path: Path) -> None:
    path = tmp_path / "mono.wav"
    sf.write(str(path), np.zeros(SR, dtype=np.float32), SR)
    m = probe(path)
    assert list(iter_stereo_blocks(m, LayoutPolicy.DOWNMIX, 4800)) == []


def test_iter_stereo_blocks_yields_for_stereo(tmp_path: Path) -> None:
    path = tmp_path / "stereo.wav"
    sf.write(str(path), np.zeros((SR, 2), dtype=np.float32), SR)
    m = probe(path)
    blocks = list(iter_stereo_blocks(m, LayoutPolicy.DOWNMIX, 4800))
    assert blocks
    assert all(b.shape[1] == 2 for b in blocks)
