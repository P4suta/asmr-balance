"""Tests for :mod:`asmr_balance.metrics.band`."""

from __future__ import annotations

import math

import numpy as np
import pytest

from asmr_balance.graph.types import RawBlock
from asmr_balance.metrics.band import BandImbalanceReducer
from asmr_balance.nodes.bandsplit import BANDS, BandedFrame, ThirdOctaveBandSplit


def test_empty_stream_yields_nan_everywhere() -> None:
    r = BandImbalanceReducer()
    m = r.finalize()
    assert math.isnan(m.low)
    assert math.isnan(m.low_mid)
    assert math.isnan(m.high_mid)
    assert math.isnan(m.high)
    for v in m.third_octave.values():
        assert math.isnan(v)


def test_balanced_input_yields_zero_dB_imbalance() -> None:
    """Equal L and R energy in every band ⇒ 0 dB per band, 0 dB roll-up."""
    n = 100
    arr = np.ones((n, 2), dtype=np.float64)
    frame = BandedFrame({b.name: arr.copy() for b in BANDS})
    r = BandImbalanceReducer()
    r.update(frame)
    m = r.finalize()
    assert m.low == pytest.approx(0.0, abs=1e-12)
    assert m.low_mid == pytest.approx(0.0, abs=1e-12)
    assert m.high_mid == pytest.approx(0.0, abs=1e-12)
    assert m.high == pytest.approx(0.0, abs=1e-12)
    for v in m.third_octave.values():
        assert v == pytest.approx(0.0, abs=1e-12)


def test_one_band_louder_on_left_emits_positive_dB() -> None:
    n = 100
    frame: dict[str, np.ndarray] = {}
    for b in BANDS:
        if b.name == "b_1000hz":
            arr = np.column_stack([np.ones(n) * 2.0, np.ones(n) * 1.0])
        else:
            arr = np.ones((n, 2))
        frame[b.name] = arr
    r = BandImbalanceReducer()
    r.update(BandedFrame(frame))
    m = r.finalize()
    # 1 kHz band L²=4, R²=1 → 10 log10(4) ≈ 6.02 dB
    assert m.third_octave["b_1000hz"] == pytest.approx(10.0 * math.log10(4.0), abs=1e-9)
    # Other low_mid bands are balanced; aggregate is dominated by 1 kHz contribution.
    assert m.low_mid > 0.0


def test_rollup_equals_partition_sum() -> None:
    """The 4-band aggregate must equal the explicit partition sum of band energies."""
    rng = np.random.default_rng(seed=42)
    sr = 48000
    samples = rng.standard_normal((sr // 4, 2)).astype(np.float32) * 0.5  # 0.25 s
    samples[:, 0] *= 1.5  # make L slightly louder
    bs = ThirdOctaveBandSplit(sample_rate=sr)
    frames = bs.process(RawBlock(samples))
    r = BandImbalanceReducer()
    for frame in frames:
        r.update(frame)
    m = r.finalize()
    # Independently compute the expected 4-band rollup from the same sums.
    partition = r.partition
    for slot_name, members in (
        ("low", partition.low),
        ("low_mid", partition.low_mid),
        ("high_mid", partition.high_mid),
        ("high", partition.high),
    ):
        l_sum = sum(r._sum_l_sq[n] for n in members)
        r_sum = sum(r._sum_r_sq[n] for n in members)
        expected_db = 10.0 * math.log10(l_sum / r_sum)
        actual_db = getattr(m, slot_name)
        assert actual_db == pytest.approx(expected_db, abs=1e-12)
