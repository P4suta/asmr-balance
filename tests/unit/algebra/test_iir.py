"""Unit tests for the type-state IIR pair.

These tests assert (a) that the two-class lifecycle (Uninit → Steady) holds
at runtime, (b) that an unprimed filter cannot ``step`` (no such attribute),
and (c) that scaling by the first sample yields the correct steady-state for
a constant input.
"""

from __future__ import annotations

import numpy as np
import pytest
import scipy.signal as sps

from asmr_balance.algebra.iir import IIRFactory, SteadyIIR, UninitializedIIR


def _trivial_lpf_sos() -> np.ndarray:
    """First-order Butterworth lowpass at fc=0.1 (normalized) for tests."""
    return np.asarray(sps.butter(2, 0.1, output="sos"), dtype=np.float64)


def test_factory_builds_uninitialised_filter() -> None:
    factory = IIRFactory(sos=_trivial_lpf_sos())
    f = factory.build()
    assert isinstance(f, UninitializedIIR)
    assert f.sos is factory.sos


def test_uninitialised_lacks_step_attribute() -> None:
    factory = IIRFactory(sos=_trivial_lpf_sos())
    f = factory.build()
    assert not hasattr(f, "step")


def test_prime_returns_steady_filter() -> None:
    factory = IIRFactory(sos=_trivial_lpf_sos())
    steady = factory.build().prime(first_sample=0.5)
    assert isinstance(steady, SteadyIIR)
    # zi must be exactly the scaled template (scipy contract).
    expected_zi = sps.sosfilt_zi(factory.sos) * 0.5
    np.testing.assert_array_equal(steady.zi, expected_zi)


def test_step_produces_constant_output_for_constant_input() -> None:
    """When primed with x0, feeding more x0s yields output ≈ x0 * DC gain."""
    sos = _trivial_lpf_sos()
    factory = IIRFactory(sos=sos)
    x0 = 1.0
    steady = factory.build().prime(first_sample=x0)
    samples = np.full(200, x0, dtype=np.float64)
    out, _ = steady.step(samples)
    # After steady-state init, output of constant-input lowpass equals input * dc_gain ≈ 1.0.
    np.testing.assert_allclose(out, np.full_like(out, x0), rtol=0, atol=1e-9)


def test_step_returns_new_steady_with_advanced_zi() -> None:
    sos = _trivial_lpf_sos()
    factory = IIRFactory(sos=sos)
    steady0 = factory.build().prime(first_sample=0.0)
    samples = np.array([1.0, -1.0, 0.5, -0.5], dtype=np.float64)
    out, steady1 = steady0.step(samples)
    # The returned state must be a fresh frozen instance (not the same object).
    assert steady1 is not steady0
    assert isinstance(steady1, SteadyIIR)
    assert steady1.sos is sos
    # Output shape and dtype contract.
    assert out.shape == samples.shape
    assert out.dtype == np.float64


def test_step_chain_matches_single_call() -> None:
    """sosfilt is exactly associative under split/concat — verify."""
    sos = _trivial_lpf_sos()
    rng = np.random.default_rng(seed=0)
    samples = rng.standard_normal(1024)
    factory = IIRFactory(sos=sos)
    # Single call.
    steady = factory.build().prime(first_sample=float(samples[0]))
    out_full, _ = steady.step(samples)
    # Two-chunk split.
    steady2 = factory.build().prime(first_sample=float(samples[0]))
    out_a, steady2 = steady2.step(samples[:300])
    out_b, _ = steady2.step(samples[300:])
    out_split = np.concatenate([out_a, out_b])
    np.testing.assert_allclose(out_split, out_full, rtol=0, atol=1e-12)


def test_factory_can_be_reused_to_produce_independent_filters() -> None:
    factory = IIRFactory(sos=_trivial_lpf_sos())
    a = factory.build()
    b = factory.build()
    # Distinct objects, same coefficients.
    assert a is not b
    assert a.sos is b.sos
    assert np.array_equal(a.zi_template, b.zi_template)


def test_steady_filter_is_frozen() -> None:
    factory = IIRFactory(sos=_trivial_lpf_sos())
    steady = factory.build().prime(first_sample=1.0)
    with pytest.raises(AttributeError):
        steady.sos = factory.sos  # type: ignore[misc]


def test_uninitialised_filter_is_frozen() -> None:
    factory = IIRFactory(sos=_trivial_lpf_sos())
    f = factory.build()
    with pytest.raises(AttributeError):
        f.sos = factory.sos  # type: ignore[misc]
