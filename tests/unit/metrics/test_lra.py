"""Tests for :mod:`asmr_balance.metrics.lra`."""

from __future__ import annotations

import math

import pytest

from asmr_balance.graph.types import ShortTermZBlock
from asmr_balance.metrics.lra import LRAReducer


def _push(r: LRAReducer, z_l: float, z_r: float, n: int) -> None:
    for _ in range(n):
        r.update(ShortTermZBlock((z_l, z_r)))


def test_empty_stream_returns_nan() -> None:
    r = LRAReducer()
    m = r.finalize()
    assert math.isnan(m.lra_lu)
    assert math.isnan(m.max_short_term_lufs)


def test_constant_loudness_yields_zero_lra() -> None:
    r = LRAReducer()
    _push(r, z_l=0.04, z_r=0.04, n=100)
    m = r.finalize()
    assert m.lra_lu == pytest.approx(0.0, abs=1e-9)


def test_max_short_term_reflects_loudest_block() -> None:
    r = LRAReducer()
    _push(r, z_l=0.001, z_r=0.001, n=50)
    _push(r, z_l=0.1, z_r=0.1, n=50)
    m = r.finalize()
    # Loudest is z=0.2 stereo → ≈ -7.7 LUFS.
    expected_loudest = -0.691 + 10.0 * math.log10(0.2)
    assert m.max_short_term_lufs == pytest.approx(expected_loudest, abs=1e-9)


def test_two_level_stream_yields_nonzero_lra() -> None:
    """A bimodal short-term distribution should produce LRA ≈ difference of levels."""
    r = LRAReducer()
    _push(r, z_l=0.1, z_r=0.1, n=100)  # ≈ -7.7 LUFS
    _push(r, z_l=0.01, z_r=0.01, n=100)  # ≈ -17.7 LUFS
    m = r.finalize()
    assert m.lra_lu > 0.0
    # Both bins exceed the relative -20 LU gate (mean ≈ -12.7), so percentiles
    # span both regions.
    assert 5.0 < m.lra_lu < 15.0
