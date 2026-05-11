"""Tests for ``asmr_balance.analyzers``."""

from __future__ import annotations

import math

import numpy as np

from asmr_balance.analyzers import build_analyzers
from asmr_balance.analyzers.correlation_imbalance import CorrelationImbalanceAnalyzer
from asmr_balance.analyzers.lufs_imbalance import LufsImbalanceAnalyzer, _safe_delta
from asmr_balance.config import Config

SR = 48000


def _stereo_sine(duration: float, freq: float, amp_l: float, amp_r: float) -> np.ndarray:
    n = int(duration * SR)
    t = np.arange(n, dtype=np.float64) / SR
    left = (amp_l * np.sin(2.0 * math.pi * freq * t)).astype(np.float32)
    right = (amp_r * np.sin(2.0 * math.pi * freq * t)).astype(np.float32)
    return np.column_stack([left, right])


def test_lufs_analyzer_emits_delta_lu_for_balanced_signal() -> None:
    an = LufsImbalanceAnalyzer(sample_rate=SR)
    an.push(_stereo_sine(2.0, 1000.0, 0.5, 0.5))
    out = an.finalize()
    assert abs(out["delta_lu"]) < 0.01


def test_lufs_analyzer_emits_panned_delta_lu() -> None:
    an = LufsImbalanceAnalyzer(sample_rate=SR)
    an.push(_stereo_sine(2.0, 1000.0, 0.5, 0.5 / 4.0))
    out = an.finalize()
    assert 11.5 < out["delta_lu"] < 12.5


def test_safe_delta_both_inf_returns_nan() -> None:
    assert math.isnan(_safe_delta(float("-inf"), float("-inf")))


def test_safe_delta_one_inf_returns_nan() -> None:
    assert math.isnan(_safe_delta(float("-inf"), -10.0))
    assert math.isnan(_safe_delta(-10.0, float("-inf")))


def test_safe_delta_finite_subtracts() -> None:
    assert _safe_delta(-5.0, -8.0) == 3.0


def test_correlation_analyzer_basic() -> None:
    an = CorrelationImbalanceAnalyzer()
    an.push(_stereo_sine(0.5, 1000.0, 0.3, 0.3))
    out = an.finalize()
    assert math.isclose(out["pearson_r"], 1.0, abs_tol=1e-6)


def test_correlation_analyzer_empty_block_noop() -> None:
    an = CorrelationImbalanceAnalyzer()
    an.push(np.zeros((0, 2), dtype=np.float32))
    out = an.finalize()
    assert math.isnan(out["pearson_r"])


def test_build_analyzers_returns_five_for_default_config() -> None:
    analyzers = build_analyzers(Config(), sample_rate=SR)
    assert len(analyzers) == 5
    names = {a.name for a in analyzers}
    assert names == {
        "lufs_imbalance",
        "correlation_imbalance",
        "band_imbalance",
        "sliding_imbalance",
        "phase_coherence",
    }
