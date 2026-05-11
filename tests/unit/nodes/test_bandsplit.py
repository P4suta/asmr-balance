"""Tests for :mod:`asmr_balance.nodes.bandsplit`."""

from __future__ import annotations

import math
from itertools import pairwise

import numpy as np
import pytest

from asmr_balance.graph.types import RawBlock
from asmr_balance.nodes.bandsplit import (
    BANDS,
    FourBandPartition,
    ThirdOctaveBandSplit,
)


def test_band_table_has_31_entries() -> None:
    assert len(BANDS) == 31


def test_band_centres_span_20hz_to_20khz() -> None:
    assert BANDS[0].centre_hz == 20.0
    assert BANDS[-1].centre_hz == 20000.0


def test_band_centres_are_strictly_increasing() -> None:
    for a, b in pairwise(BANDS):
        assert a.centre_hz < b.centre_hz


def test_band_edges_obey_third_octave_ratio() -> None:
    ratio = 2.0 ** (1.0 / 6.0)
    for b in BANDS:
        assert b.high_edge_hz == pytest.approx(b.centre_hz * ratio, rel=1e-12)
        assert b.low_edge_hz == pytest.approx(b.centre_hz / ratio, rel=1e-12)


def test_partition_assignment_is_exhaustive_and_disjoint() -> None:
    p = FourBandPartition.from_bands(BANDS)
    total = len(p.low) + len(p.low_mid) + len(p.high_mid) + len(p.high)
    assert total == 31
    all_names = set(b.name for b in BANDS)
    assert set(p.low).union(p.low_mid, p.high_mid, p.high) == all_names


def test_partition_cutoffs() -> None:
    p = FourBandPartition.from_bands(BANDS)
    # low: centres < 250 Hz → 20..200 Hz = 11 bands
    assert len(p.low) == 11
    # low_mid: 250..1600 = 9 bands
    assert len(p.low_mid) == 9
    # high_mid: 2000..6300 = 6 bands
    assert len(p.high_mid) == 6
    # high: 8000..20000 = 5 bands
    assert len(p.high) == 5


def test_band_names_are_unique() -> None:
    names = [b.name for b in BANDS]
    assert len(names) == len(set(names))


def test_filter_emits_one_frame_per_input() -> None:
    f = ThirdOctaveBandSplit(sample_rate=48000)
    block = np.zeros((4800, 2), dtype=np.float32)
    frames = f.process(RawBlock(block))
    assert len(frames) == 1
    assert set(frames[0].keys()) == {b.name for b in BANDS}


def test_filter_frame_shapes_and_dtypes() -> None:
    f = ThirdOctaveBandSplit(sample_rate=48000)
    block = np.random.default_rng(seed=0).standard_normal((4800, 2)).astype(np.float32)
    frame = f.process(RawBlock(block))[0]
    for name, arr in frame.items():
        assert arr.shape == (4800, 2), f"band {name} has unexpected shape {arr.shape}"
        assert arr.dtype == np.float64


def test_band_isolates_its_centre_frequency() -> None:
    """A pure tone at band-centre passes nearly intact; bands far away attenuate."""
    sr = 48000
    n = sr
    t = np.arange(n) / sr
    target_fc = 1000.0
    sig = np.sin(2 * math.pi * target_fc * t).astype(np.float32)
    block = np.column_stack([sig, sig])
    f = ThirdOctaveBandSplit(sample_rate=sr)
    frame = f.process(RawBlock(block))[0]
    # b_1000hz should be near full amplitude after transient.
    band_1k = frame["b_1000hz"]
    far_band = frame["b_25hz"]
    in_rms = float(np.sqrt(np.mean(sig**2)))
    rms_1k = float(np.sqrt(np.mean(band_1k[2000:, 0] ** 2)))
    rms_far = float(np.sqrt(np.mean(far_band[2000:, 0] ** 2)))
    assert rms_1k == pytest.approx(in_rms, rel=0.05)
    assert rms_far < in_rms * 0.001


def test_filter_empty_block_is_noop() -> None:
    f = ThirdOctaveBandSplit(sample_rate=48000)
    assert f.process(RawBlock(np.empty((0, 2), dtype=np.float32))) == []


def test_filter_flush_emits_nothing() -> None:
    f = ThirdOctaveBandSplit(sample_rate=48000)
    f.process(RawBlock(np.zeros((100, 2), dtype=np.float32)))
    assert f.flush() == []
