"""Tests for ``asmr_balance.dsp.correlation`` (Welford + Mid/Side)."""

from __future__ import annotations

import math

import numpy as np
import pytest

from asmr_balance.dsp.correlation import MidSideRMS, StereoStats, WelfordCorrelation


def test_welford_empty_returns_nan() -> None:
    w = WelfordCorrelation()
    assert math.isnan(w.correlation)


def test_welford_zero_variance_returns_nan() -> None:
    w = WelfordCorrelation()
    x = np.full(100, 0.5, dtype=np.float64)
    w.update(x, x)
    assert math.isnan(w.correlation)


def test_welford_perfect_correlation() -> None:
    rng = np.random.default_rng(seed=0)
    x = rng.standard_normal(2000)
    w = WelfordCorrelation()
    w.update(x, x)
    assert math.isclose(w.correlation, 1.0, abs_tol=1e-9)


def test_welford_anticorrelated() -> None:
    rng = np.random.default_rng(seed=1)
    x = rng.standard_normal(2000)
    w = WelfordCorrelation()
    w.update(x, -x)
    assert math.isclose(w.correlation, -1.0, abs_tol=1e-9)


def test_welford_shape_mismatch_raises() -> None:
    w = WelfordCorrelation()
    with pytest.raises(ValueError, match="shape mismatch"):
        w.update(np.zeros(10), np.zeros(11))


def test_welford_empty_chunk_noop() -> None:
    w = WelfordCorrelation()
    w.update(np.asarray([]), np.asarray([]))
    assert w.n == 0


def test_welford_single_chunk_matches_numpy() -> None:
    rng = np.random.default_rng(seed=42)
    x = rng.standard_normal(1024)
    y = rng.standard_normal(1024)
    w = WelfordCorrelation()
    w.update(x, y)
    expected = float(np.corrcoef(x, y)[0, 1])
    assert math.isclose(w.correlation, expected, abs_tol=1e-9)


def test_welford_multiple_chunks_equivalent_to_single() -> None:
    rng = np.random.default_rng(seed=99)
    x = rng.standard_normal(4096)
    y = rng.standard_normal(4096)
    w_single = WelfordCorrelation()
    w_single.update(x, y)
    w_split = WelfordCorrelation()
    for x_chunk, y_chunk in zip(np.array_split(x, 7), np.array_split(y, 7), strict=True):
        w_split.update(x_chunk, y_chunk)
    assert math.isclose(w_split.correlation, w_single.correlation, abs_tol=1e-9)


def test_mid_side_empty_returns_nan() -> None:
    ms = MidSideRMS()
    assert math.isnan(ms.ms_ratio_db)


def test_mid_side_pure_mono_returns_inf() -> None:
    ms = MidSideRMS()
    left = np.full(1000, 0.3, dtype=np.float32)
    ms.update(left, left)
    assert math.isinf(ms.ms_ratio_db)


def test_mid_side_phase_inverted_returns_nan() -> None:
    ms = MidSideRMS()
    rng = np.random.default_rng(seed=7)
    sig = rng.standard_normal(1000).astype(np.float32) * 0.1
    ms.update(sig, -sig)  # M = 0 → sum_m_sq = 0
    assert math.isnan(ms.ms_ratio_db)


def test_mid_side_normal_stereo_finite() -> None:
    rng = np.random.default_rng(seed=8)
    left = rng.standard_normal(2048).astype(np.float32) * 0.2
    right = left * 0.6 + rng.standard_normal(2048).astype(np.float32) * 0.05
    ms = MidSideRMS()
    ms.update(left, right)
    assert math.isfinite(ms.ms_ratio_db)


def test_mid_side_shape_mismatch_raises() -> None:
    ms = MidSideRMS()
    with pytest.raises(ValueError, match="shape mismatch"):
        ms.update(np.zeros(10), np.zeros(11))


def test_mid_side_empty_chunk_noop() -> None:
    ms = MidSideRMS()
    ms.update(np.asarray([]), np.asarray([]))
    assert ms.n == 0


def test_stereo_stats_composes_both() -> None:
    rng = np.random.default_rng(seed=11)
    left = rng.standard_normal(1024).astype(np.float32)
    right = left.copy()
    stats = StereoStats()
    stats.update(left, right)
    assert math.isclose(stats.correlation.correlation, 1.0, abs_tol=1e-9)
    assert math.isinf(stats.mid_side.ms_ratio_db)
