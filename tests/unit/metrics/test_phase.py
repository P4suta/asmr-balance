"""Tests for :mod:`asmr_balance.metrics.phase`."""

from __future__ import annotations

import math

import numpy as np
import pytest

from asmr_balance.graph.types import LowPassBlock
from asmr_balance.metrics.phase import LowPhaseCoherenceReducer


def test_empty_stream_returns_nan() -> None:
    r = LowPhaseCoherenceReducer()
    assert math.isnan(r.finalize().low_phase_coherence)


def test_identical_lowpass_yields_one() -> None:
    rng = np.random.default_rng(seed=0)
    sig = rng.standard_normal(2000).astype(np.float64)
    block = LowPassBlock(np.column_stack([sig, sig]))
    r = LowPhaseCoherenceReducer()
    r.update(block)
    assert r.finalize().low_phase_coherence == pytest.approx(1.0, abs=1e-9)


def test_inverted_lowpass_yields_minus_one() -> None:
    rng = np.random.default_rng(seed=1)
    sig = rng.standard_normal(2000).astype(np.float64)
    block = LowPassBlock(np.column_stack([sig, -sig]))
    r = LowPhaseCoherenceReducer()
    r.update(block)
    assert r.finalize().low_phase_coherence == pytest.approx(-1.0, abs=1e-9)


def test_chunked_update_matches_bulk_update() -> None:
    rng = np.random.default_rng(seed=2)
    samples = rng.standard_normal((4096, 2))
    bulk = LowPhaseCoherenceReducer()
    bulk.update(LowPassBlock(samples))
    chunked = LowPhaseCoherenceReducer()
    for chunk in np.array_split(samples, 5, axis=0):
        chunked.update(LowPassBlock(np.ascontiguousarray(chunk)))
    assert bulk.finalize().low_phase_coherence == pytest.approx(
        chunked.finalize().low_phase_coherence, abs=1e-9
    )


def test_empty_block_is_noop() -> None:
    r = LowPhaseCoherenceReducer()
    r.update(LowPassBlock(np.empty((0, 2), dtype=np.float64)))
    assert math.isnan(r.finalize().low_phase_coherence)
