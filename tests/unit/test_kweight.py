"""Branch-coverage tests for ``asmr_balance.dsp.kweight``."""

from __future__ import annotations

import numpy as np
import pytest
import scipy.signal

from asmr_balance.dsp.kweight import (
    _high_pass_biquad,
    _high_shelf_biquad,
    apply_kweighting,
    make_kweighting_sos,
)


def test_make_sos_returns_two_sections_at_48k() -> None:
    sos = make_kweighting_sos(48000)
    assert sos.shape == (2, 6)


def test_make_sos_rejects_zero_sample_rate() -> None:
    with pytest.raises(ValueError, match="positive"):
        make_kweighting_sos(0)


def test_make_sos_rejects_negative_sample_rate() -> None:
    with pytest.raises(ValueError, match="positive"):
        make_kweighting_sos(-44100)


def test_make_sos_rejects_below_nyquist_for_filters() -> None:
    with pytest.raises(ValueError, match="Nyquist"):
        make_kweighting_sos(2000)


def test_high_shelf_biquad_normalisation_at_dc() -> None:
    # At very low f (DC), the high-shelf is approximately unity gain
    sos = np.asarray([_high_shelf_biquad(4.0, 1 / np.sqrt(2), 1500.0, 48000)])
    _w, h = scipy.signal.sosfreqz(sos, worN=[10.0], fs=48000)
    assert abs(abs(h[0]) - 1.0) < 0.05


def test_high_shelf_biquad_boost_above_corner() -> None:
    sos = np.asarray([_high_shelf_biquad(4.0, 1 / np.sqrt(2), 1500.0, 48000)])
    _w, h = scipy.signal.sosfreqz(sos, worN=[20000.0], fs=48000)
    db = 20.0 * np.log10(abs(h[0]))
    assert 3.5 < db < 4.5


def test_high_pass_biquad_attenuates_dc() -> None:
    sos = np.asarray([_high_pass_biquad(0.5, 38.0, 48000)])
    _w, h = scipy.signal.sosfreqz(sos, worN=[1.0], fs=48000)
    db = 20.0 * np.log10(abs(h[0]) + 1e-30)
    assert db < -20.0


def test_high_pass_biquad_passes_treble() -> None:
    sos = np.asarray([_high_pass_biquad(0.5, 38.0, 48000)])
    _w, h = scipy.signal.sosfreqz(sos, worN=[2000.0], fs=48000)
    db = 20.0 * np.log10(abs(h[0]))
    assert abs(db) < 0.5


def test_apply_kweighting_rejects_2d_input() -> None:
    sos = make_kweighting_sos(48000)
    with pytest.raises(ValueError, match="1-D"):
        apply_kweighting(np.zeros((2, 10)), sos)


def test_apply_kweighting_empty_input_returns_empty_with_zi() -> None:
    sos = make_kweighting_sos(48000)
    out, zi = apply_kweighting(np.asarray([], dtype=np.float32), sos)
    assert out.size == 0
    assert zi.shape == (sos.shape[0], 2)


def test_apply_kweighting_initialises_zi_from_first_sample() -> None:
    sos = make_kweighting_sos(48000)
    sig = np.full(100, 0.5, dtype=np.float32)
    out, _ = apply_kweighting(sig, sos, zi=None)
    # steady-state init from sig[0]=0.5 means a constant signal yields a small
    # transient followed by sustained near-zero (because RLB is high-pass).
    assert out.shape == (100,)
    assert abs(float(out[-1])) < 0.05


def test_apply_kweighting_reuses_provided_zi() -> None:
    sos = make_kweighting_sos(48000)
    rng = np.random.default_rng(seed=0)
    sig = rng.standard_normal(200).astype(np.float32) * 0.1
    out1, zi1 = apply_kweighting(sig[:100], sos, zi=None)
    out2, _ = apply_kweighting(sig[100:], sos, zi=zi1)
    # Concatenated should match running the whole array in one go
    out_full, _ = apply_kweighting(sig, sos, zi=None)
    np.testing.assert_allclose(np.concatenate([out1, out2]), out_full, atol=1e-9)
