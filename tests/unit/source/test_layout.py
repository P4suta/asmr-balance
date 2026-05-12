"""Tests for :mod:`asmr_balance.source.layout`."""

from __future__ import annotations

import math

import numpy as np
import pytest

from asmr_balance.source.adt import LayoutPolicy
from asmr_balance.source.layout import fold_to_stereo

_INV_SQRT2 = 1.0 / math.sqrt(2.0)


def test_mono_returns_none() -> None:
    arr = np.ones((10, 1), dtype=np.float32)
    assert fold_to_stereo(arr, n_channels=1, policy=LayoutPolicy.DOWNMIX) is None


def test_stereo_passes_through() -> None:
    arr = np.arange(20, dtype=np.float32).reshape(10, 2)
    out = fold_to_stereo(arr, n_channels=2, policy=LayoutPolicy.DOWNMIX)
    assert out is not None
    np.testing.assert_array_equal(out, arr)


@pytest.mark.parametrize(
    "policy",
    [LayoutPolicy.DOWNMIX, LayoutPolicy.FL_FR, LayoutPolicy.NATIVE_WEIGHTED],
)
def test_5_1_downmix_combines_center_and_back(policy: LayoutPolicy) -> None:
    """For DOWNMIX, the BS.775 formula applies; FL_FR / NATIVE_WEIGHTED drop extras."""
    # FL, FR, FC, LFE, BL, BR
    frame = np.array(
        [
            [1.0, 2.0, 4.0, 0.0, 8.0, 16.0],
        ],
        dtype=np.float32,
    )
    out = fold_to_stereo(frame, n_channels=6, policy=policy)
    assert out is not None
    if policy is LayoutPolicy.DOWNMIX:
        # left = FL + 1/√2 * FC + 0.5 * BL
        # right = FR + 1/√2 * FC + 0.5 * BR
        expected_l = 1.0 + _INV_SQRT2 * 4.0 + 0.5 * 8.0
        expected_r = 2.0 + _INV_SQRT2 * 4.0 + 0.5 * 16.0
        assert out[0, 0] == pytest.approx(expected_l, rel=1e-6)
        assert out[0, 1] == pytest.approx(expected_r, rel=1e-6)
    else:
        assert out[0, 0] == 1.0
        assert out[0, 1] == 2.0


def test_layout_skip_drops_multichannel() -> None:
    frame = np.zeros((10, 6), dtype=np.float32)
    assert fold_to_stereo(frame, n_channels=6, policy=LayoutPolicy.SKIP) is None


def test_quad_4channel_takes_first_two() -> None:
    """4-channel falls below the 5-channel downmix threshold → take FL/FR."""
    frame = np.tile(np.array([[1.0, 2.0, 3.0, 4.0]], dtype=np.float32), (5, 1))
    out = fold_to_stereo(frame, n_channels=4, policy=LayoutPolicy.DOWNMIX)
    assert out is not None
    np.testing.assert_array_equal(out, np.tile([[1.0, 2.0]], (5, 1)))


def test_5_0_no_lfe_still_downmixes() -> None:
    """5.0 layout: FL FR FC BL BR (no LFE)."""
    frame = np.array([[1.0, 2.0, 4.0, 8.0, 16.0]], dtype=np.float32)
    out = fold_to_stereo(frame, n_channels=5, policy=LayoutPolicy.DOWNMIX)
    assert out is not None
    # frame[:, 4] is BL (index 4) per the legacy formula.
    expected_l = 1.0 + _INV_SQRT2 * 4.0 + 0.5 * 16.0
    expected_r = 2.0 + _INV_SQRT2 * 4.0  # BR index 5 missing → 0
    assert out[0, 0] == pytest.approx(expected_l, rel=1e-6)
    assert out[0, 1] == pytest.approx(expected_r, rel=1e-6)


def test_output_is_contiguous_float32() -> None:
    frame = np.zeros((10, 6), dtype=np.float32)
    out = fold_to_stereo(frame, n_channels=6, policy=LayoutPolicy.DOWNMIX)
    assert out is not None
    assert out.dtype == np.float32
    assert out.flags["C_CONTIGUOUS"]
