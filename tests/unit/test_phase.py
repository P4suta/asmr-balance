"""Tests for ``asmr_balance.dsp.phase`` and ``analyzers.phase_coherence``."""

from __future__ import annotations

import math

import numpy as np
import pytest

from asmr_balance.analyzers.phase_coherence import PhaseCoherenceAnalyzer
from asmr_balance.dsp.phase import LowPhaseCoherence, make_lowpass_sos

SR = 48000


def test_make_lowpass_sos_rejects_too_low_rate() -> None:
    with pytest.raises(ValueError, match="too low"):
        make_lowpass_sos(sample_rate=200)


def test_make_lowpass_sos_returns_sos() -> None:
    sos = make_lowpass_sos(SR)
    assert sos.shape[1] == 6


def test_phase_coherence_empty_returns_nan() -> None:
    lp = LowPhaseCoherence(sample_rate=SR)
    assert math.isnan(lp.finalize())


def test_phase_coherence_empty_push_is_noop() -> None:
    lp = LowPhaseCoherence(sample_rate=SR)
    lp.push(np.zeros((0, 2), dtype=np.float32))
    assert math.isnan(lp.finalize())


def test_phase_coherence_identical_low_signals_near_one() -> None:
    lp = LowPhaseCoherence(sample_rate=SR)
    n = SR * 2
    rng = np.random.default_rng(seed=0)
    bass = rng.standard_normal(n).astype(np.float32) * 0.2
    lp.push(np.column_stack([bass, bass]))
    assert lp.finalize() > 0.99


def test_phase_coherence_phase_inverted_low_signals_near_minus_one() -> None:
    lp = LowPhaseCoherence(sample_rate=SR)
    n = SR * 2
    rng = np.random.default_rng(seed=1)
    bass = rng.standard_normal(n).astype(np.float32) * 0.2
    lp.push(np.column_stack([bass, -bass]))
    assert lp.finalize() < -0.99


def test_phase_analyzer_emits_low_phase_coherence_key() -> None:
    an = PhaseCoherenceAnalyzer(sample_rate=SR)
    rng = np.random.default_rng(seed=2)
    bass = rng.standard_normal(SR).astype(np.float32) * 0.1
    an.push(np.column_stack([bass, bass]))
    out = an.finalize()
    assert "low_phase_coherence" in out


def test_phase_split_push_equivalent_to_single() -> None:
    rng = np.random.default_rng(seed=3)
    bass = rng.standard_normal(SR).astype(np.float32) * 0.15
    block = np.column_stack([bass, bass])

    single = LowPhaseCoherence(sample_rate=SR)
    single.push(block)
    full = single.finalize()

    split = LowPhaseCoherence(sample_rate=SR)
    for chunk in np.array_split(block, 7, axis=0):
        split.push(np.ascontiguousarray(chunk))
    partial = split.finalize()

    assert math.isclose(full, partial, abs_tol=1e-6)
