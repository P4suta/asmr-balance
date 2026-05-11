"""Hypothesis property tests for the BS.1770 K-weighted pipeline.

Tests focus on invariants we expect the implementation to satisfy:
- ``L = R`` ⇒ ``delta_lu ≈ 0``
- scaling both channels by a constant gain ⇒ ``delta_lu`` unchanged
- swapping channels ⇒ ``delta_lu`` sign-flipped
"""

from __future__ import annotations

import math

import numpy as np
import pytest
from hypothesis import HealthCheck, given, settings, strategies as st

from asmr_balance.dsp.lufs import measure_lufs


@pytest.mark.property
@given(
    seed=st.integers(min_value=0, max_value=2**16 - 1),
    gain=st.floats(min_value=0.05, max_value=0.6, allow_nan=False, allow_infinity=False),
    sample_rate=st.sampled_from([44100, 48000]),
)
@settings(max_examples=15, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_identical_channels_yield_zero_delta(seed: int, gain: float, sample_rate: int) -> None:
    rng = np.random.default_rng(seed)
    n = int(0.6 * sample_rate)  # >= one 400 ms block
    mono = (rng.standard_normal(n) * gain).astype(np.float32)
    stereo = np.column_stack([mono, mono])
    out = measure_lufs(stereo, sample_rate)
    if math.isfinite(out["single_channel_lufs_l"]):
        delta = out["single_channel_lufs_l"] - out["single_channel_lufs_r"]
        assert abs(delta) < 1e-6


@pytest.mark.property
@given(
    seed=st.integers(min_value=0, max_value=2**16 - 1),
    gain_scale=st.floats(min_value=0.5, max_value=2.0, allow_nan=False, allow_infinity=False),
)
@settings(max_examples=10, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_uniform_gain_preserves_delta(seed: int, gain_scale: float) -> None:
    rng = np.random.default_rng(seed)
    sr = 48000
    n = int(0.6 * sr)
    left = (rng.standard_normal(n) * 0.2).astype(np.float32)
    right = (rng.standard_normal(n) * 0.1).astype(np.float32)
    stereo = np.column_stack([left, right])
    out_a = measure_lufs(stereo, sr)
    out_b = measure_lufs((stereo * gain_scale).astype(np.float32), sr)
    if all(math.isfinite(out_a[k]) for k in ("single_channel_lufs_l", "single_channel_lufs_r")):
        delta_a = out_a["single_channel_lufs_l"] - out_a["single_channel_lufs_r"]
        delta_b = out_b["single_channel_lufs_l"] - out_b["single_channel_lufs_r"]
        assert abs(delta_a - delta_b) < 0.1


@pytest.mark.property
@given(seed=st.integers(min_value=0, max_value=2**16 - 1))
@settings(max_examples=10, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_channel_swap_flips_delta_sign(seed: int) -> None:
    rng = np.random.default_rng(seed)
    sr = 48000
    n = int(0.6 * sr)
    left = (rng.standard_normal(n) * 0.2).astype(np.float32)
    right = (rng.standard_normal(n) * 0.05).astype(np.float32)
    stereo = np.column_stack([left, right])
    out_lr = measure_lufs(stereo, sr)
    out_rl = measure_lufs(np.column_stack([right, left]), sr)
    if all(math.isfinite(out_lr[k]) for k in ("single_channel_lufs_l", "single_channel_lufs_r")):
        delta_lr = out_lr["single_channel_lufs_l"] - out_lr["single_channel_lufs_r"]
        delta_rl = out_rl["single_channel_lufs_l"] - out_rl["single_channel_lufs_r"]
        assert abs(delta_lr + delta_rl) < 0.01
