"""Tests for :mod:`asmr_balance.metrics.correlation`."""

from __future__ import annotations

import math

import numpy as np
import pytest

from asmr_balance.graph.types import RawBlock
from asmr_balance.metrics.correlation import StereoCorrelationReducer


def test_empty_stream_returns_nan() -> None:
    r = StereoCorrelationReducer()
    m = r.finalize()
    assert math.isnan(m.pearson_r)
    assert math.isnan(m.ms_ratio_db)


def test_identical_channels_yield_pearson_one() -> None:
    rng = np.random.default_rng(seed=0)
    sig = rng.standard_normal(4800).astype(np.float32)
    block = RawBlock(np.column_stack([sig, sig]))
    r = StereoCorrelationReducer()
    r.update(block)
    m = r.finalize()
    assert m.pearson_r == pytest.approx(1.0, abs=1e-9)


def test_inverted_channels_yield_pearson_minus_one() -> None:
    rng = np.random.default_rng(seed=1)
    sig = rng.standard_normal(4800).astype(np.float32)
    block = RawBlock(np.column_stack([sig, -sig]))
    r = StereoCorrelationReducer()
    r.update(block)
    m = r.finalize()
    assert m.pearson_r == pytest.approx(-1.0, abs=1e-9)


def test_independent_channels_yield_near_zero_pearson() -> None:
    rng = np.random.default_rng(seed=2)
    left = rng.standard_normal(48000).astype(np.float32)
    right = rng.standard_normal(48000).astype(np.float32)
    block = RawBlock(np.column_stack([left, right]))
    r = StereoCorrelationReducer()
    r.update(block)
    m = r.finalize()
    assert abs(m.pearson_r) < 0.05


def test_chunked_update_matches_bulk_update() -> None:
    """Welford CGL must be associative under chunking."""
    rng = np.random.default_rng(seed=3)
    samples = rng.standard_normal((4096, 2)).astype(np.float32)
    bulk = StereoCorrelationReducer()
    bulk.update(RawBlock(samples))
    chunked = StereoCorrelationReducer()
    for chunk in np.array_split(samples, 7, axis=0):
        chunked.update(RawBlock(np.ascontiguousarray(chunk)))
    m_bulk = bulk.finalize()
    m_chunked = chunked.finalize()
    assert m_bulk.pearson_r == pytest.approx(m_chunked.pearson_r, abs=1e-9)
    assert m_bulk.ms_ratio_db == pytest.approx(m_chunked.ms_ratio_db, abs=1e-9)


def test_mid_side_ratio_for_identical_channels_is_positive_infinity() -> None:
    """Identical L, R ⇒ side = 0 ⇒ M/S ratio is +inf."""
    sig = np.ones(1000, dtype=np.float32)
    block = RawBlock(np.column_stack([sig, sig]))
    r = StereoCorrelationReducer()
    r.update(block)
    m = r.finalize()
    assert math.isinf(m.ms_ratio_db)
    assert m.ms_ratio_db > 0


def test_mid_side_ratio_for_inverted_channels_is_negative_infinity() -> None:
    """Identical L, -L ⇒ mid = 0 ⇒ M/S ratio for non-zero side reaches -inf in dB."""
    sig = np.ones(1000, dtype=np.float32)
    block = RawBlock(np.column_stack([sig, -sig]))
    r = StereoCorrelationReducer()
    r.update(block)
    m = r.finalize()
    assert math.isinf(m.ms_ratio_db)
    assert m.ms_ratio_db < 0


def test_empty_block_is_noop() -> None:
    r = StereoCorrelationReducer()
    r.update(RawBlock(np.empty((0, 2), dtype=np.float32)))
    m = r.finalize()
    assert math.isnan(m.pearson_r)
