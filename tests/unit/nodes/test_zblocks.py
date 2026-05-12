"""Tests for :mod:`asmr_balance.nodes.zblocks`."""

from __future__ import annotations

import numpy as np
import pytest

from asmr_balance.graph.types import KWeightedBlock
from asmr_balance.nodes.zblocks import ShortTermZBlocksFilter, ZBlocksFilter


def _const(n: int, l: float, r: float) -> KWeightedBlock:
    arr = np.empty((n, 2), dtype=np.float64)
    arr[:, 0] = l
    arr[:, 1] = r
    return KWeightedBlock(arr)


def test_zblocks_rejects_invalid_sample_rate() -> None:
    with pytest.raises(ValueError, match="positive"):
        ZBlocksFilter(sample_rate=0)


def test_zblocks_emits_first_block_after_400ms() -> None:
    """At 48 kHz, 400 ms = 19200 samples; first emission expected at that point."""
    f = ZBlocksFilter(sample_rate=48000)
    # 100 ms = 4800 samples per push; first three pushes accumulate, fourth emits.
    for _ in range(3):
        emitted = f.process(_const(4800, l=0.5, r=-0.5))
        assert emitted == []
    emitted = f.process(_const(4800, l=0.5, r=-0.5))
    assert len(emitted) == 1
    z_l, z_r = emitted[0]
    # mean-square of constant 0.5 is 0.25, of -0.5 is 0.25.
    assert z_l == pytest.approx(0.25, rel=1e-12)
    assert z_r == pytest.approx(0.25, rel=1e-12)


def test_zblocks_hop_emits_one_per_100ms_after_first_window() -> None:
    f = ZBlocksFilter(sample_rate=48000)
    # Get past the first window.
    for _ in range(4):
        f.process(_const(4800, l=0.0, r=0.0))
    # Now each subsequent 100 ms push emits exactly one block.
    for _ in range(10):
        emitted = f.process(_const(4800, l=0.1, r=0.2))
        assert len(emitted) == 1


def test_zblocks_chunked_push_equivalent_to_bulk_push() -> None:
    """Pushing one big block must emit the same z-pairs as many small blocks."""
    rng = np.random.default_rng(seed=1)
    samples = rng.standard_normal((48000, 2))  # 1 second @ 48 kHz
    f_bulk = ZBlocksFilter(sample_rate=48000)
    bulk = f_bulk.process(KWeightedBlock(samples))
    f_chunked = ZBlocksFilter(sample_rate=48000)
    chunked: list[tuple[float, float]] = []
    for chunk in np.array_split(samples, 17, axis=0):
        chunked.extend(f_chunked.process(KWeightedBlock(np.ascontiguousarray(chunk))))
    assert len(bulk) == len(chunked)
    for a, b in zip(bulk, chunked, strict=True):
        assert a[0] == pytest.approx(b[0], rel=1e-12)
        assert a[1] == pytest.approx(b[1], rel=1e-12)


def test_zblocks_empty_input_emits_nothing() -> None:
    f = ZBlocksFilter(sample_rate=48000)
    empty = np.empty((0, 2), dtype=np.float64)
    assert f.process(KWeightedBlock(empty)) == []


def test_zblocks_flush_emits_nothing() -> None:
    f = ZBlocksFilter(sample_rate=48000)
    f.process(_const(4800, 1.0, 1.0))
    assert f.flush() == []


def test_zblocks_count_for_one_second() -> None:
    """1 s @ 48 kHz with 400 ms / 100 ms hop yields 7 blocks (at t=0.4,0.5,...,1.0)."""
    f = ZBlocksFilter(sample_rate=48000)
    samples = np.ones((48000, 2), dtype=np.float64) * 0.3
    emitted = f.process(KWeightedBlock(samples))
    assert len(emitted) == 7


def test_shortterm_emits_first_block_after_3s() -> None:
    f = ShortTermZBlocksFilter(sample_rate=48000)
    # 3 s = 144000 samples. Push 29 x 100 ms (= 2.9 s) -> no emission.
    for _ in range(29):
        emitted = f.process(_const(4800, l=0.1, r=0.1))
        assert emitted == []
    # 30th push completes 3 s.
    emitted = f.process(_const(4800, l=0.1, r=0.1))
    assert len(emitted) == 1


def test_shortterm_constant_value() -> None:
    f = ShortTermZBlocksFilter(sample_rate=48000)
    samples = np.full((144000, 2), 0.2, dtype=np.float64)
    emitted = f.process(KWeightedBlock(samples))
    assert len(emitted) == 1
    z_l, z_r = emitted[0]
    assert z_l == pytest.approx(0.04, rel=1e-12)
    assert z_r == pytest.approx(0.04, rel=1e-12)
