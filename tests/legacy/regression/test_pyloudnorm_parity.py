"""Regression parity: ``LUFS_I_stereo`` ↔ ``pyloudnorm.Meter.integrated_loudness``.

Per ADR-0002, our K-weighting + gating implementation is independent of
pyloudnorm at runtime, but we validate against it offline within ``±0.1 LU``
on canonical signals. This proves we have not silently drifted from BS.1770.
"""

from __future__ import annotations

import math

import numpy as np
import pyloudnorm as pyln
import pytest

from asmr_balance.dsp.lufs import measure_lufs


def _stereo_sine(amp_l: float, amp_r: float, freq: float, duration: float, sr: int) -> np.ndarray:
    n = int(duration * sr)
    t = np.arange(n, dtype=np.float64) / sr
    left = amp_l * np.sin(2.0 * math.pi * freq * t)
    right = amp_r * np.sin(2.0 * math.pi * freq * t)
    return np.column_stack([left, right]).astype(np.float32)


def _pyln_integrated(stereo: np.ndarray, sr: int) -> float:
    # pyloudnorm wants (N, 2) float (any), and returns LUFS (or -inf for silence)
    meter = pyln.Meter(sr)
    return float(meter.integrated_loudness(stereo.astype(np.float64)))


TOLERANCE_LU = 0.1


@pytest.mark.regression
@pytest.mark.parametrize(
    ("amp_l", "amp_r", "freq", "duration"),
    [
        (0.5, 0.5, 1000.0, 4.0),  # balanced loud
        (0.1, 0.1, 1000.0, 4.0),  # balanced quiet (still above gate)
        (0.5, 0.125, 1000.0, 4.0),  # 12 dB panned
        (0.5, 0.0, 1000.0, 4.0),  # full L, zero R
        (0.3, 0.3, 100.0, 4.0),  # low-frequency
        (0.3, 0.3, 8000.0, 4.0),  # high-frequency
    ],
)
def test_lufs_i_stereo_matches_pyloudnorm(
    amp_l: float, amp_r: float, freq: float, duration: float
) -> None:
    sr = 48000
    stereo = _stereo_sine(amp_l, amp_r, freq, duration, sr)
    ours = measure_lufs(stereo, sr)["lufs_i_stereo"]
    theirs = _pyln_integrated(stereo, sr)
    if math.isinf(theirs):
        assert math.isinf(ours)
        return
    assert abs(ours - theirs) < TOLERANCE_LU, f"|{ours:.4f} - {theirs:.4f}| > {TOLERANCE_LU}"


@pytest.mark.regression
def test_lufs_parity_on_pink_noise() -> None:
    sr = 48000
    rng = np.random.default_rng(seed=12345)
    n = int(5.0 * sr)
    # 1/√f-shaped gaussian in frequency domain → approximate pink noise
    freqs = np.fft.rfftfreq(n, 1.0 / sr)
    freqs[0] = 1.0
    spec = np.fft.rfft(rng.standard_normal(n)) / np.sqrt(freqs)
    mono = np.fft.irfft(spec, n=n)
    mono = (mono / np.max(np.abs(mono)) * 0.25).astype(np.float32)
    stereo = np.column_stack([mono, mono])
    ours = measure_lufs(stereo, sr)["lufs_i_stereo"]
    theirs = _pyln_integrated(stereo, sr)
    assert abs(ours - theirs) < TOLERANCE_LU


@pytest.mark.regression
def test_lufs_parity_silence_both_infinite() -> None:
    sr = 48000
    silence = np.zeros((sr * 2, 2), dtype=np.float32)
    ours = measure_lufs(silence, sr)["lufs_i_stereo"]
    theirs = _pyln_integrated(silence, sr)
    assert ours == float("-inf")
    assert math.isinf(theirs)
