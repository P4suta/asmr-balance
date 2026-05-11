"""Branch-coverage tests for ``asmr_balance.dsp.gating``."""

from __future__ import annotations

import math

import numpy as np
import pytest

from asmr_balance.dsp.gating import (
    BlockAccumulator,
    GateConfig,
    _block_levels,
    _mean_to_lufs,
    integrate_gated,
    integrated_from_z_mean,
    loudness_from_z,
)

# --- scalar helpers ---------------------------------------------------------


def test_loudness_from_z_positive() -> None:
    # z = 1.0 → L = -0.691
    assert math.isclose(loudness_from_z(1.0), -0.691, abs_tol=1e-9)


def test_loudness_from_z_zero() -> None:
    assert loudness_from_z(0.0) == float("-inf")


def test_loudness_from_z_negative() -> None:
    assert loudness_from_z(-0.01) == float("-inf")


def test_loudness_from_z_nan() -> None:
    assert loudness_from_z(float("nan")) == float("-inf")


def test_integrated_from_z_mean_delegates() -> None:
    assert math.isclose(integrated_from_z_mean(1.0), loudness_from_z(1.0))


# --- BlockAccumulator -------------------------------------------------------


def test_block_accumulator_rejects_invalid_rate() -> None:
    with pytest.raises(ValueError, match="positive"):
        BlockAccumulator(sample_rate=0)


def test_block_accumulator_sizes_at_48k() -> None:
    acc = BlockAccumulator(sample_rate=48000)
    assert acc.block_size == 48000 * 4 // 10
    assert acc.hop_size == 48000 // 10


def test_block_accumulator_push_empty_is_noop() -> None:
    acc = BlockAccumulator(sample_rate=48000)
    acc.push(np.asarray([], dtype=np.float64))
    assert acc.z_blocks == []


def test_block_accumulator_no_emit_when_buffer_short() -> None:
    acc = BlockAccumulator(sample_rate=48000)
    acc.push(np.ones(100, dtype=np.float64))
    assert acc.z_blocks == []


def test_block_accumulator_emits_blocks_with_tail() -> None:
    acc = BlockAccumulator(sample_rate=48000)
    # 0.4s + 0.05s extra → 1 block, 0.05s tail
    samples = np.ones(int(48000 * 0.45), dtype=np.float64)
    acc.push(samples)
    assert len(acc.z_blocks) == 1
    assert acc.z_blocks[0] == pytest.approx(1.0)


def test_block_accumulator_emits_blocks_no_tail() -> None:
    acc = BlockAccumulator(sample_rate=48000)
    samples = np.ones(int(48000 * 0.4), dtype=np.float64)
    acc.push(samples)
    assert len(acc.z_blocks) == 1


def test_block_accumulator_overlap_75_percent() -> None:
    acc = BlockAccumulator(sample_rate=48000)
    # 1 s of ones → 7 blocks (positions 0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6),
    # block at 0.7 would need samples up to 1.1s which we don't have
    samples = np.ones(48000, dtype=np.float64)
    acc.push(samples)
    expected_blocks = 7
    assert len(acc.z_blocks) == expected_blocks


def test_block_accumulator_split_push_equals_single_push() -> None:
    acc_single = BlockAccumulator(sample_rate=48000)
    acc_split = BlockAccumulator(sample_rate=48000)
    rng = np.random.default_rng(seed=42)
    signal = rng.standard_normal(48000).astype(np.float64) * 0.1
    acc_single.push(signal)
    # split into 7 uneven chunks
    chunks = np.array_split(signal, 7)
    for chunk in chunks:
        acc_split.push(chunk)
    assert len(acc_single.z_blocks) == len(acc_split.z_blocks)
    np.testing.assert_allclose(acc_single.z_blocks, acc_split.z_blocks, atol=1e-12)


# --- integrate_gated --------------------------------------------------------


def test_integrate_gated_empty_returns_minus_inf() -> None:
    out = integrate_gated([], [])
    for value in out.values():
        assert value == float("-inf")


def test_integrate_gated_mismatched_lengths() -> None:
    with pytest.raises(ValueError, match="block counts differ"):
        integrate_gated([1.0, 2.0], [1.0])


def test_integrate_gated_all_below_abs_gate_is_minus_inf() -> None:
    # tiny z → very negative L → all below -70 LUFS
    z = [1e-10] * 5
    out = integrate_gated(z, z)
    assert out["lufs_i_stereo"] == float("-inf")
    assert out["single_channel_lufs_l"] == float("-inf")
    assert out["single_channel_lufs_r"] == float("-inf")
    # ungated still produces a finite value (no gate applied)
    assert math.isfinite(out["single_channel_lufs_ungated_l"])


def test_integrate_gated_balanced_signal() -> None:
    z = [1.0] * 10  # L = -0.691, well above -70 LUFS
    out = integrate_gated(z, z)
    assert math.isclose(out["single_channel_lufs_l"], -0.691, abs_tol=1e-6)
    assert math.isclose(out["single_channel_lufs_r"], -0.691, abs_tol=1e-6)
    # stereo sum: z_stereo = 2.0 → L = -0.691 + 10·log10(2) ≈ 2.319
    assert math.isclose(out["lufs_i_stereo"], -0.691 + 10.0 * math.log10(2.0), abs_tol=1e-6)


def test_integrate_gated_imbalanced_signal() -> None:
    z_l = [1.0] * 10
    z_r = [0.25] * 10  # 6 dB lower → delta should be ~6 LU
    out = integrate_gated(z_l, z_r)
    delta = out["single_channel_lufs_l"] - out["single_channel_lufs_r"]
    expected_delta_lu = 6.0
    assert math.isclose(delta, expected_delta_lu, abs_tol=0.05)


def test_block_levels_handles_zero_and_positive() -> None:
    z = np.asarray([0.0, 1.0, 2.0], dtype=np.float64)
    levels = _block_levels(z)
    assert levels[0] == float("-inf")
    assert math.isfinite(levels[1])
    assert math.isfinite(levels[2])


def test_mean_to_lufs_empty_mask_is_minus_inf() -> None:
    z = np.asarray([1.0, 2.0], dtype=np.float64)
    mask = np.zeros(2, dtype=bool)
    assert _mean_to_lufs(z, mask) == float("-inf")


def test_mean_to_lufs_partial_mask() -> None:
    z = np.asarray([1.0, 4.0], dtype=np.float64)
    mask = np.asarray([True, False])
    assert math.isclose(_mean_to_lufs(z, mask), -0.691, abs_tol=1e-6)


def test_gate_config_overrides_threshold() -> None:
    z = [1e-10] * 5
    out_default = integrate_gated(z, z, GateConfig(abs_gate_lufs=-70.0))
    out_lenient = integrate_gated(z, z, GateConfig(abs_gate_lufs=-200.0))
    assert out_default["single_channel_lufs_l"] == float("-inf")
    assert math.isfinite(out_lenient["single_channel_lufs_l"])
