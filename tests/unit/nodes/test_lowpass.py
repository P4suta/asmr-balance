"""Tests for :mod:`asmr_balance.nodes.lowpass`."""

from __future__ import annotations

import math

import numpy as np
import pytest

from asmr_balance.algebra.iir import SteadyIIR, UninitializedIIR
from asmr_balance.graph.types import RawBlock
from asmr_balance.nodes.lowpass import LowPassFilter, make_lowpass_sos


def test_sos_design_succeeds() -> None:
    sos = make_lowpass_sos(order=4, cutoff_hz=300.0, sample_rate=48000)
    assert sos.shape[1] == 6
    assert np.isfinite(sos).all()


def test_sos_rejects_bad_inputs() -> None:
    with pytest.raises(ValueError, match="positive"):
        make_lowpass_sos(order=4, cutoff_hz=300.0, sample_rate=0)
    with pytest.raises(ValueError, match="Nyquist"):
        make_lowpass_sos(order=4, cutoff_hz=30000.0, sample_rate=48000)
    with pytest.raises(ValueError, match="Nyquist"):
        make_lowpass_sos(order=4, cutoff_hz=-1.0, sample_rate=48000)


def test_filter_constructs_unprimed() -> None:
    f = LowPassFilter(sample_rate=48000, cutoff_hz=300.0, order=4)
    assert isinstance(f._state_l, UninitializedIIR)
    assert isinstance(f._state_r, UninitializedIIR)


def test_filter_primes_on_first_block() -> None:
    f = LowPassFilter(sample_rate=48000)
    block = np.full((100, 2), 0.5, dtype=np.float32)
    _ = f.process(RawBlock(block))
    assert isinstance(f._state_l, SteadyIIR)


def test_lowpass_passes_30hz() -> None:
    sr = 48000
    n = sr  # 1 s
    t = np.arange(n) / sr
    sig = np.sin(2 * math.pi * 30.0 * t).astype(np.float32)
    block = np.column_stack([sig, sig])
    f = LowPassFilter(sample_rate=sr, cutoff_hz=300.0, order=4)
    out = f.process(RawBlock(block))[0]
    in_rms = float(np.sqrt(np.mean(sig**2)))
    out_rms = float(np.sqrt(np.mean(out[1000:, 0] ** 2)))
    # 30 Hz is well below 300 Hz cutoff → almost full pass.
    assert out_rms == pytest.approx(in_rms, rel=0.02)


def test_lowpass_rejects_5khz() -> None:
    sr = 48000
    n = sr
    t = np.arange(n) / sr
    sig = np.sin(2 * math.pi * 5000.0 * t).astype(np.float32)
    block = np.column_stack([sig, sig])
    f = LowPassFilter(sample_rate=sr, cutoff_hz=300.0, order=4)
    out = f.process(RawBlock(block))[0]
    out_rms = float(np.sqrt(np.mean(out[2000:, 0] ** 2)))
    # 5 kHz is far above 300 Hz cutoff for a 4th-order Butterworth → heavy attenuation.
    assert out_rms < 0.01


def test_filter_empty_block_is_noop() -> None:
    f = LowPassFilter(sample_rate=48000)
    empty = np.empty((0, 2), dtype=np.float32)
    assert f.process(RawBlock(empty)) == []
    assert isinstance(f._state_l, UninitializedIIR)


def test_filter_flush_emits_nothing() -> None:
    f = LowPassFilter(sample_rate=48000)
    f.process(RawBlock(np.ones((100, 2), dtype=np.float32)))
    assert f.flush() == []
