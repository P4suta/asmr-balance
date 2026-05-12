"""Tests for :mod:`asmr_balance.metrics.loudness`.

The numerical fidelity to BS.1770-5 / pyloudnorm is enforced by
``tests/legacy/regression/test_pyloudnorm_parity.py``. Here we only verify
behavioral contracts (NaN propagation, gating math, empty-stream behavior).
"""

from __future__ import annotations

import math

import pytest

from asmr_balance.graph.types import ZBlock
from asmr_balance.metrics.loudness import GateConfig, IntegratedLoudnessReducer


def _const_z_stream(reducer: IntegratedLoudnessReducer, z_l: float, z_r: float, n: int) -> None:
    for _ in range(n):
        reducer.update(ZBlock((z_l, z_r)))


def test_empty_stream_returns_all_negative_infinity() -> None:
    r = IntegratedLoudnessReducer()
    m = r.finalize()
    assert m.lufs_i_stereo == float("-inf")
    assert m.single_channel_lufs_l == float("-inf")
    assert m.single_channel_lufs_r == float("-inf")
    assert math.isnan(m.delta_lu)
    assert math.isnan(m.delta_lu_ungated)


def test_balanced_pink_yields_zero_delta() -> None:
    r = IntegratedLoudnessReducer()
    _const_z_stream(r, z_l=0.05, z_r=0.05, n=100)
    m = r.finalize()
    assert m.delta_lu == pytest.approx(0.0, abs=1e-12)
    assert m.lufs_i_stereo == pytest.approx(-0.691 + 10.0 * math.log10(0.1))


def test_pan_left_yields_positive_delta() -> None:
    r = IntegratedLoudnessReducer()
    _const_z_stream(r, z_l=0.1, z_r=0.01, n=100)
    m = r.finalize()
    assert m.delta_lu == pytest.approx(10.0, abs=1e-9)


def test_silent_channel_propagates_nan_delta() -> None:
    """One channel at z=0 → its LUFS is -inf, delta is NaN."""
    r = IntegratedLoudnessReducer()
    _const_z_stream(r, z_l=0.1, z_r=0.0, n=100)
    m = r.finalize()
    assert m.single_channel_lufs_l != float("-inf")
    assert m.single_channel_lufs_r == float("-inf")
    assert math.isnan(m.delta_lu)


def test_absolute_gate_drops_quiet_blocks() -> None:
    """Quiet (-80 LUFS) blocks must not affect the integrated mean."""
    r_with = IntegratedLoudnessReducer()
    _const_z_stream(r_with, z_l=0.1, z_r=0.1, n=50)
    base = r_with.finalize().lufs_i_stereo

    r_with_quiet = IntegratedLoudnessReducer()
    _const_z_stream(r_with_quiet, z_l=0.1, z_r=0.1, n=50)
    # Very quiet blocks below -70 LUFS abs gate.
    _const_z_stream(r_with_quiet, z_l=1e-9, z_r=1e-9, n=50)
    after = r_with_quiet.finalize().lufs_i_stereo

    assert after == pytest.approx(base, abs=1e-6)


def test_gate_config_drops_all_below_strict_abs_gate() -> None:
    """An absolute gate set above every block's loudness rejects everything → -inf."""
    cfg = GateConfig(abs_gate_lufs=10.0)  # absurdly high; nothing passes
    r = IntegratedLoudnessReducer(gate=cfg)
    _const_z_stream(r, z_l=0.1, z_r=0.1, n=50)
    m = r.finalize()
    assert m.lufs_i_stereo == float("-inf")
    assert m.single_channel_lufs_l == float("-inf")
    # Ungated path is unaffected.
    assert m.single_channel_lufs_ungated_l != float("-inf")


def test_ungated_path_is_arithmetic_mean() -> None:
    """The ungated single-channel LUFS is plain L_offset + 10 log10(mean z)."""
    r = IntegratedLoudnessReducer()
    _const_z_stream(r, z_l=0.04, z_r=0.04, n=50)
    m = r.finalize()
    expected = -0.691 + 10.0 * math.log10(0.04)
    assert m.single_channel_lufs_ungated_l == pytest.approx(expected, abs=1e-9)
    assert m.single_channel_lufs_ungated_r == pytest.approx(expected, abs=1e-9)
