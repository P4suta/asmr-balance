"""Tests for :mod:`asmr_balance.metrics.dynamics`."""

from __future__ import annotations

import math

import numpy as np
import pytest

from asmr_balance.graph.types import OversampledBlock
from asmr_balance.metrics.dynamics import TruePeakReducer, derive_psr_db
from asmr_balance.metrics.subtrees import LRAMetrics


def test_empty_stream_yields_zero_peaks() -> None:
    r = TruePeakReducer()
    peak = r.finalize()
    assert peak.max_abs_l == 0.0
    assert peak.max_abs_r == 0.0


def test_silent_input_yields_neg_inf_dbtp() -> None:
    r = TruePeakReducer()
    r.update(OversampledBlock(np.zeros((100, 2), dtype=np.float64)))
    peak = r.finalize()
    dyn = derive_psr_db(peak, LRAMetrics(lra_lu=0.0, max_short_term_lufs=-30.0))
    assert dyn.true_peak_dbtp_l == float("-inf")
    assert dyn.true_peak_dbtp_r == float("-inf")
    assert math.isnan(dyn.psr_db)


def test_unit_peak_yields_zero_dbtp() -> None:
    r = TruePeakReducer()
    arr = np.zeros((10, 2), dtype=np.float64)
    arr[5, 0] = 1.0
    arr[3, 1] = -0.5
    r.update(OversampledBlock(arr))
    peak = r.finalize()
    dyn = derive_psr_db(peak, LRAMetrics(lra_lu=4.0, max_short_term_lufs=-10.0))
    assert dyn.true_peak_dbtp_l == pytest.approx(0.0, abs=1e-9)
    assert dyn.true_peak_dbtp_r == pytest.approx(-6.020599913279624, abs=1e-9)
    assert dyn.true_peak_dbtp_max == pytest.approx(0.0, abs=1e-9)
    # PSR = 0 - (-10) = 10 dB
    assert dyn.psr_db == pytest.approx(10.0, abs=1e-9)


def test_psr_is_nan_when_lra_short_term_is_nan() -> None:
    r = TruePeakReducer()
    arr = np.full((10, 2), 0.5, dtype=np.float64)
    r.update(OversampledBlock(arr))
    peak = r.finalize()
    dyn = derive_psr_db(peak, LRAMetrics(lra_lu=float("nan"), max_short_term_lufs=float("nan")))
    assert math.isnan(dyn.psr_db)
    # Peak fields still valid.
    assert dyn.true_peak_dbtp_l == pytest.approx(20.0 * math.log10(0.5), abs=1e-9)


def test_running_max_updates_correctly() -> None:
    r = TruePeakReducer()
    r.update(OversampledBlock(np.array([[0.1, 0.2], [0.3, 0.05]], dtype=np.float64)))
    r.update(OversampledBlock(np.array([[0.2, 0.5], [-0.4, 0.1]], dtype=np.float64)))
    peak = r.finalize()
    assert peak.max_abs_l == pytest.approx(0.4, abs=1e-12)
    assert peak.max_abs_r == pytest.approx(0.5, abs=1e-12)


def test_empty_block_is_noop() -> None:
    r = TruePeakReducer()
    r.update(OversampledBlock(np.empty((0, 2), dtype=np.float64)))
    peak = r.finalize()
    assert peak.max_abs_l == 0.0


def test_negative_peak_max_uses_absolute_value() -> None:
    r = TruePeakReducer()
    r.update(OversampledBlock(np.array([[-0.7, 0.3], [0.2, -0.9]], dtype=np.float64)))
    peak = r.finalize()
    assert peak.max_abs_l == pytest.approx(0.7, abs=1e-12)
    assert peak.max_abs_r == pytest.approx(0.9, abs=1e-12)
