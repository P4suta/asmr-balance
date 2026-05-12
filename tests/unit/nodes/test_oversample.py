"""Tests for :mod:`asmr_balance.nodes.oversample`."""

from __future__ import annotations

import math

import numpy as np
import pytest

from asmr_balance.graph.types import RawBlock
from asmr_balance.nodes.oversample import Oversample4xPolyphase


def test_output_is_4x_input_length() -> None:
    f = Oversample4xPolyphase()
    block = np.zeros((100, 2), dtype=np.float32)
    out = f.process(RawBlock(block))[0]
    assert out.shape == (400, 2)
    assert out.dtype == np.float64


def test_empty_input_is_noop() -> None:
    f = Oversample4xPolyphase()
    assert f.process(RawBlock(np.empty((0, 2), dtype=np.float32))) == []


def test_flush_emits_nothing() -> None:
    f = Oversample4xPolyphase()
    f.process(RawBlock(np.ones((100, 2), dtype=np.float32)))
    assert f.flush() == []


def test_zero_input_yields_zero_output() -> None:
    f = Oversample4xPolyphase()
    block = np.zeros((1024, 2), dtype=np.float32)
    out = f.process(RawBlock(block))[0]
    np.testing.assert_array_equal(out, np.zeros_like(out))


def test_chunked_input_matches_concatenated_state() -> None:
    """Two chunks → identical to one big chunk (post-warmup tail)."""
    rng = np.random.default_rng(seed=0)
    samples = rng.standard_normal((4096, 2)).astype(np.float32)
    f_bulk = Oversample4xPolyphase()
    out_bulk = f_bulk.process(RawBlock(samples))[0]
    f_chunked = Oversample4xPolyphase()
    a = f_chunked.process(RawBlock(samples[:1500]))[0]
    b = f_chunked.process(RawBlock(samples[1500:]))[0]
    out_chunked = np.concatenate([a, b], axis=0)
    assert out_chunked.shape == out_bulk.shape
    np.testing.assert_allclose(out_chunked, out_bulk, rtol=0, atol=1e-10)


def test_sine_at_5khz_preserves_peak_amplitude() -> None:
    """A 5 kHz sine at amplitude 1.0 should appear in the oversampled stream
    with peak ≈ 1.0 (after FIR transient settles)."""
    sr = 48000
    n = sr
    t = np.arange(n) / sr
    sig = np.sin(2 * math.pi * 5000.0 * t).astype(np.float32)
    block = np.column_stack([sig, sig])
    f = Oversample4xPolyphase()
    out = f.process(RawBlock(block))[0]
    # After transient (~50 samples at 4x), peak should be ≈ 1.0 within ±1%.
    tail = out[400:]
    peak = float(np.max(np.abs(tail)))
    assert peak == pytest.approx(1.0, abs=0.02)
