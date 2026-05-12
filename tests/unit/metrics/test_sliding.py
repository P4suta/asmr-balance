"""Tests for :mod:`asmr_balance.metrics.sliding`."""

from __future__ import annotations

import math

import pytest

from asmr_balance.graph.types import ZBlock
from asmr_balance.metrics.sliding import SlidingImbalanceReducer


def _push(r: SlidingImbalanceReducer, z_l: float, z_r: float, n: int) -> None:
    for _ in range(n):
        r.update(ZBlock((z_l, z_r)))


def test_empty_stream_returns_nan() -> None:
    r = SlidingImbalanceReducer()
    m = r.finalize()
    assert math.isnan(m.max_lu)
    assert math.isnan(m.p95_lu)
    assert math.isnan(m.std_lu)
    assert math.isnan(m.t_max_sec)


def test_balanced_stream_zero_delta() -> None:
    r = SlidingImbalanceReducer()
    _push(r, z_l=0.1, z_r=0.1, n=30)
    m = r.finalize()
    assert m.max_lu == pytest.approx(0.0, abs=1e-9)
    assert m.std_lu == pytest.approx(0.0, abs=1e-9)


def test_panned_stream_yields_constant_delta() -> None:
    r = SlidingImbalanceReducer()
    _push(r, z_l=0.1, z_r=0.01, n=30)  # 10 LU difference
    m = r.finalize()
    assert m.max_lu == pytest.approx(10.0, abs=1e-9)
    assert m.p95_lu == pytest.approx(10.0, abs=1e-9)


def test_t_max_indexes_the_loudest_imbalance_block() -> None:
    r = SlidingImbalanceReducer()
    _push(r, z_l=0.1, z_r=0.1, n=10)
    # The 11th block (index 10, t = 10 * 0.1 = 1.0 sec) has a big imbalance.
    r.update(ZBlock((1.0, 0.01)))
    _push(r, z_l=0.1, z_r=0.1, n=10)
    m = r.finalize()
    assert m.t_max_sec == pytest.approx(1.0, abs=1e-9)


def test_silent_blocks_are_filtered_out() -> None:
    """Blocks with z=0 on either side must not pollute the statistic."""
    r = SlidingImbalanceReducer()
    _push(r, z_l=0.0, z_r=0.0, n=5)
    _push(r, z_l=0.1, z_r=0.1, n=5)
    m = r.finalize()
    # The first silent blocks are dropped; the rest are balanced.
    assert m.max_lu == pytest.approx(0.0, abs=1e-9)
