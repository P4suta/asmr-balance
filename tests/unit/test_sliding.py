"""Tests for ``asmr_balance.dsp.sliding`` and ``analyzers.sliding_imbalance``."""

from __future__ import annotations

import math

import numpy as np

from asmr_balance.analyzers.sliding_imbalance import SlidingImbalanceAnalyzer
from asmr_balance.dsp.sliding import SlidingImbalance

SR = 48000


def _sine(duration: float, freq: float, amp: float, sr: int = SR) -> np.ndarray:
    n = int(duration * sr)
    t = np.arange(n, dtype=np.float64) / sr
    return (amp * np.sin(2.0 * np.pi * freq * t)).astype(np.float32)


def test_sliding_empty_returns_nan() -> None:
    s = SlidingImbalance(sample_rate=SR)
    out = s.finalize()
    for value in out.values():
        assert math.isnan(value)


def test_sliding_empty_push_is_noop() -> None:
    s = SlidingImbalance(sample_rate=SR)
    s.push(np.zeros((0, 2), dtype=np.float32))
    out = s.finalize()
    for value in out.values():
        assert math.isnan(value)


def test_sliding_silent_signal_returns_nan() -> None:
    s = SlidingImbalance(sample_rate=SR)
    silent = np.zeros((SR * 2, 2), dtype=np.float32)
    s.push(silent)
    out = s.finalize()
    for value in out.values():
        assert math.isnan(value)


def test_sliding_balanced_signal_has_small_max() -> None:
    s = SlidingImbalance(sample_rate=SR)
    sine = _sine(1.5, 1000.0, 0.4)
    block = np.column_stack([sine, sine])
    s.push(block)
    out = s.finalize()
    assert out["sliding_max_lu"] < 1.0


def test_sliding_panned_signal_records_high_max() -> None:
    s = SlidingImbalance(sample_rate=SR)
    left = _sine(1.5, 1000.0, 0.5)
    right = _sine(1.5, 1000.0, 0.5 / 4.0)
    s.push(np.column_stack([left, right]))
    out = s.finalize()
    # 12 dB amplitude diff → ~12 LU per block
    assert 10.0 < out["sliding_max_lu"] < 14.0
    assert out["sliding_std_lu"] < 1.0


def test_sliding_local_bias_detected_when_global_balanced() -> None:
    """First half L-loud, second half R-loud → integrated ΔLU ≈ 0 but per-block max large."""
    s = SlidingImbalance(sample_rate=SR)
    duration = 2.0
    left_loud = _sine(duration / 2.0, 1000.0, 0.5)
    left_quiet = _sine(duration / 2.0, 1000.0, 0.05)
    left = np.concatenate([left_loud, left_quiet])
    right = np.concatenate([left_quiet, left_loud])
    block = np.column_stack([left, right]).astype(np.float32)
    s.push(block)
    out = s.finalize()
    assert out["sliding_max_lu"] > 10.0


def test_sliding_analyzer_emits_all_keys() -> None:
    an = SlidingImbalanceAnalyzer(sample_rate=SR)
    sine = _sine(0.5, 1000.0, 0.3)
    an.push(np.column_stack([sine, sine]))
    out = an.finalize()
    assert set(out) == {"sliding_max_lu", "sliding_p95_lu", "sliding_std_lu", "sliding_t_max_sec"}


def test_sliding_with_partial_silence_drops_invalid_blocks() -> None:
    """Half-silent file should only report stats on the non-silent half."""
    s = SlidingImbalance(sample_rate=SR)
    silent = np.zeros((SR, 2), dtype=np.float32)
    loud_sine = _sine(1.0, 1000.0, 0.4)
    loud = np.column_stack([loud_sine, loud_sine]).astype(np.float32)
    s.push(np.concatenate([silent, loud], axis=0))
    out = s.finalize()
    assert math.isfinite(out["sliding_max_lu"])
