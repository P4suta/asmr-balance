"""Tests for :mod:`asmr_balance.nodes.kweighting`.

The SOS coefficients are the load-bearing artefact for BS.1770 parity. We
verify them against scipy reference designs and against the pyloudnorm
canonical numbers via the regression suite (in ``tests/legacy``); here we just
guarantee structural correctness and stage-typed plumbing.
"""

from __future__ import annotations

import math

import numpy as np
import pytest
import scipy.signal as sps

from asmr_balance.algebra.iir import SteadyIIR, UninitializedIIR
from asmr_balance.graph.types import RawBlock
from asmr_balance.nodes.kweighting import KWeightingFilter, make_kweighting_sos


def test_sos_shape_at_48k() -> None:
    sos = make_kweighting_sos(48000)
    assert sos.shape == (2, 6)
    assert sos.dtype == np.float64


def test_sos_is_cached() -> None:
    a = make_kweighting_sos(48000)
    b = make_kweighting_sos(48000)
    # underlying tuple is cached; arrays are constructed fresh from it but
    # are equal byte-for-byte.
    np.testing.assert_array_equal(a, b)


@pytest.mark.parametrize("sample_rate", [44100, 48000, 88200, 96000, 192000])
def test_sos_design_succeeds_for_audio_rates(sample_rate: int) -> None:
    sos = make_kweighting_sos(sample_rate)
    # No NaNs or Infs.
    assert np.isfinite(sos).all()
    # Filter is stable: poles inside the unit circle.
    for row in sos:
        b, a = row[:3], np.concatenate([[1.0], row[4:6]])
        z, p, _ = sps.tf2zpk(b, a)
        assert np.all(np.abs(p) < 1.0), f"unstable pole at sr={sample_rate}: {p}"


def test_sos_rejects_invalid_sample_rate() -> None:
    with pytest.raises(ValueError, match="positive"):
        make_kweighting_sos(0)
    with pytest.raises(ValueError, match="positive"):
        make_kweighting_sos(-48000)


def test_sos_rejects_subnyquist_sample_rate() -> None:
    with pytest.raises(ValueError, match="Nyquist"):
        make_kweighting_sos(3000)  # below 2 * 1500 Hz pre-filter centre


def test_filter_constructs_with_uninitialised_state() -> None:
    f = KWeightingFilter(sample_rate=48000)
    assert isinstance(f._state_l, UninitializedIIR)
    assert isinstance(f._state_r, UninitializedIIR)


def test_filter_transitions_to_steady_after_first_block() -> None:
    f = KWeightingFilter(sample_rate=48000)
    block = np.zeros((100, 2), dtype=np.float32)
    block[:, 0] = 0.5
    block[:, 1] = -0.5
    _ = f.process(RawBlock(block))
    assert isinstance(f._state_l, SteadyIIR)
    assert isinstance(f._state_r, SteadyIIR)


def test_filter_output_shape_and_dtype() -> None:
    f = KWeightingFilter(sample_rate=48000)
    block = np.random.default_rng(seed=0).standard_normal((4800, 2)).astype(np.float32)
    out = f.process(RawBlock(block))
    assert len(out) == 1
    assert out[0].shape == (4800, 2)
    assert out[0].dtype == np.float64


def test_filter_empty_block_is_noop() -> None:
    f = KWeightingFilter(sample_rate=48000)
    empty = np.empty((0, 2), dtype=np.float32)
    assert f.process(RawBlock(empty)) == []
    assert isinstance(f._state_l, UninitializedIIR)  # still unprimed


def test_filter_flush_emits_nothing() -> None:
    f = KWeightingFilter(sample_rate=48000)
    block = np.random.default_rng(seed=1).standard_normal((100, 2)).astype(np.float32)
    _ = f.process(RawBlock(block))
    assert f.flush() == []


def test_filter_chained_blocks_equal_single_block() -> None:
    """sosfilt is associative under chunk concatenation when zi is carried."""
    rng = np.random.default_rng(seed=42)
    samples = rng.standard_normal((4800, 2)).astype(np.float32)
    f_single = KWeightingFilter(sample_rate=48000)
    out_single = f_single.process(RawBlock(samples))[0]
    f_chunked = KWeightingFilter(sample_rate=48000)
    out_a = f_chunked.process(RawBlock(samples[:1234]))[0]
    out_b = f_chunked.process(RawBlock(samples[1234:]))[0]
    out_chunked = np.concatenate([out_a, out_b], axis=0)
    np.testing.assert_allclose(out_chunked, out_single, rtol=0, atol=1e-10)


def test_filter_dc_input_steady_state() -> None:
    """A DC input should produce ≈ 0 output after K-weighting (HPF rejects DC)."""
    block = np.full((4800, 2), 0.5, dtype=np.float32)
    f = KWeightingFilter(sample_rate=48000)
    out = f.process(RawBlock(block))[0]
    # After steady-state init at 0.5, RLB HPF rejects the constant.
    # The first sample initialises to dc steady state; remaining outputs ≈ 0.
    # We allow a transient near the boundary.
    tail = out[1000:]
    assert np.max(np.abs(tail)) < 1e-3


def test_kweighting_attenuation_below_50_hz() -> None:
    """K-weighting should heavily attenuate a 30 Hz tone."""
    sr = 48000
    n = sr  # 1 second
    t = np.arange(n) / sr
    sig = np.sin(2 * math.pi * 30.0 * t).astype(np.float32)
    block = np.column_stack([sig, sig])
    f = KWeightingFilter(sample_rate=sr)
    out = f.process(RawBlock(block))[0]
    in_rms = float(np.sqrt(np.mean(sig**2)))
    out_rms = float(np.sqrt(np.mean(out[:, 0] ** 2)))
    # RLB high-pass should give significant attenuation at 30 Hz.
    assert out_rms < in_rms * 0.5
