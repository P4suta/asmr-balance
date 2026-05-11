"""Branch-coverage tests for ``asmr_balance.dsp.lufs``."""

from __future__ import annotations

import math

import numpy as np
import pytest

from asmr_balance.dsp.gating import GateConfig
from asmr_balance.dsp.lufs import LufsAccumulator, measure_lufs


def _make_sine(duration_sec: float, freq_hz: float, amp: float, sample_rate: int) -> np.ndarray:
    n = int(duration_sec * sample_rate)
    t = np.arange(n, dtype=np.float64) / sample_rate
    return (amp * np.sin(2.0 * math.pi * freq_hz * t)).astype(np.float32)


def test_acc_rejects_non_2d_block() -> None:
    acc = LufsAccumulator(sample_rate=48000)
    bad = np.zeros(100, dtype=np.float32)
    with pytest.raises(ValueError, match="stereo"):
        acc.push(bad)


def test_acc_rejects_non_stereo_channel_count() -> None:
    acc = LufsAccumulator(sample_rate=48000)
    bad = np.zeros((100, 3), dtype=np.float32)
    with pytest.raises(ValueError, match="stereo"):
        acc.push(bad)


def test_acc_empty_block_is_noop() -> None:
    acc = LufsAccumulator(sample_rate=48000)
    acc.push(np.zeros((0, 2), dtype=np.float32))
    out = acc.finalize()
    assert out["lufs_i_stereo"] == float("-inf")


def test_acc_block_count_zero_before_400ms() -> None:
    acc = LufsAccumulator(sample_rate=48000)
    short = np.zeros((1000, 2), dtype=np.float32)
    acc.push(short)
    assert acc.block_count == 0


def test_acc_block_count_grows_with_signal() -> None:
    acc = LufsAccumulator(sample_rate=48000)
    sine_l = _make_sine(1.0, 1000.0, 0.5, 48000)
    block = np.column_stack([sine_l, sine_l])
    acc.push(block)
    assert acc.block_count >= 1


def test_measure_lufs_silence_returns_minus_inf() -> None:
    silence = np.zeros((48000, 2), dtype=np.float32)
    out = measure_lufs(silence, 48000)
    assert out["lufs_i_stereo"] == float("-inf")


def test_measure_lufs_balanced_tone_has_zero_delta() -> None:
    sine = _make_sine(2.0, 1000.0, 0.5, 48000)
    stereo = np.column_stack([sine, sine])
    out = measure_lufs(stereo, 48000)
    delta = out["single_channel_lufs_l"] - out["single_channel_lufs_r"]
    assert abs(delta) < 0.01


def test_measure_lufs_panned_left_is_louder() -> None:
    sine_loud = _make_sine(2.0, 1000.0, 0.5, 48000)
    sine_quiet = _make_sine(2.0, 1000.0, 0.5 / 4.0, 48000)  # 12 dB quieter
    stereo = np.column_stack([sine_loud, sine_quiet])
    out = measure_lufs(stereo, 48000)
    delta = out["single_channel_lufs_l"] - out["single_channel_lufs_r"]
    # 12 dB difference in amplitude → 12 LU in K-weighted gated mean
    assert 11.5 < delta < 12.5


def test_measure_lufs_ungated_finite_when_signal_present() -> None:
    sine = _make_sine(2.0, 1000.0, 0.1, 48000)
    stereo = np.column_stack([sine, sine])
    out = measure_lufs(stereo, 48000)
    assert math.isfinite(out["single_channel_lufs_ungated_l"])
    assert math.isfinite(out["single_channel_lufs_ungated_r"])


def test_acc_supports_custom_gate_config() -> None:
    acc = LufsAccumulator(sample_rate=48000, gate=GateConfig(abs_gate_lufs=-200.0))
    very_quiet = _make_sine(2.0, 1000.0, 1e-5, 48000)
    stereo = np.column_stack([very_quiet, very_quiet])
    acc.push(stereo)
    out = acc.finalize()
    # Lenient gate keeps quiet blocks → finite single-channel LUFS
    assert math.isfinite(out["single_channel_lufs_l"])


def test_acc_streaming_push_matches_one_shot() -> None:
    sine = _make_sine(2.0, 1000.0, 0.5, 48000)
    stereo = np.column_stack([sine, sine]).astype(np.float32)

    one_shot = measure_lufs(stereo, 48000)

    acc = LufsAccumulator(sample_rate=48000)
    # arbitrary, uneven chunk sizes
    splits = np.array_split(stereo, 11)
    for chunk in splits:
        acc.push(np.ascontiguousarray(chunk))
    streamed = acc.finalize()

    for key in one_shot:
        assert math.isclose(one_shot[key], streamed[key], abs_tol=1e-9), key
