"""Tests for ``asmr_balance.dsp.bands`` and ``analyzers.band_imbalance``."""

from __future__ import annotations

import math

import numpy as np
import pytest

from asmr_balance.analyzers.band_imbalance import BandImbalanceAnalyzer
from asmr_balance.dsp.bands import Band, BandImbalanceAccumulator, make_band_sos

SR = 48000


def test_make_band_sos_rejects_low_sample_rate() -> None:
    with pytest.raises(ValueError, match="too low"):
        make_band_sos(Band.HIGH, sample_rate=8000)


@pytest.mark.parametrize("band", list(Band))
def test_make_band_sos_returns_array(band: Band) -> None:
    sos = make_band_sos(band, SR)
    assert sos.shape[1] == 6


def test_band_imbalance_empty_returns_nan() -> None:
    acc = BandImbalanceAccumulator(sample_rate=SR)
    for band in Band:
        assert math.isnan(acc.imbalance_db(band))


def test_band_imbalance_empty_push_is_noop() -> None:
    acc = BandImbalanceAccumulator(sample_rate=SR)
    acc.push(np.asarray([]), np.asarray([]))
    assert math.isnan(acc.imbalance_db(Band.LOW))


def test_band_imbalance_silent_returns_nan() -> None:
    acc = BandImbalanceAccumulator(sample_rate=SR)
    silence = np.zeros(SR // 2, dtype=np.float32)
    acc.push(silence, silence)
    for band in Band:
        assert math.isnan(acc.imbalance_db(band))


def test_band_imbalance_balanced_tone_near_zero_db() -> None:
    acc = BandImbalanceAccumulator(sample_rate=SR)
    n = SR
    t = np.arange(n, dtype=np.float64) / SR
    tone = (0.3 * np.sin(2.0 * np.pi * 1500.0 * t)).astype(np.float32)
    acc.push(tone, tone)
    # 1500 Hz lives in low_mid band — should be near 0 dB
    assert abs(acc.imbalance_db(Band.LOW_MID)) < 0.1


def test_band_imbalance_pan_only_in_specific_band() -> None:
    acc = BandImbalanceAccumulator(sample_rate=SR)
    n = SR
    t = np.arange(n, dtype=np.float64) / SR
    # 5 kHz tone — high_mid band; L louder than R by ~6 dB amplitude
    left = (0.5 * np.sin(2.0 * np.pi * 5000.0 * t)).astype(np.float32)
    right = (0.25 * np.sin(2.0 * np.pi * 5000.0 * t)).astype(np.float32)
    acc.push(left, right)
    assert 5.5 < acc.imbalance_db(Band.HIGH_MID) < 6.5


def test_band_analyzer_emits_all_four_bands() -> None:
    an = BandImbalanceAnalyzer(sample_rate=SR)
    n = SR // 2
    t = np.arange(n, dtype=np.float64) / SR
    sig = (0.3 * np.sin(2.0 * np.pi * 1000.0 * t)).astype(np.float32)
    block = np.column_stack([sig, sig])
    an.push(block)
    out = an.finalize()
    assert set(out) == {
        "band_imbalance_low",
        "band_imbalance_low_mid",
        "band_imbalance_high_mid",
        "band_imbalance_high",
    }


def test_band_analyzer_empty_block_noop() -> None:
    an = BandImbalanceAnalyzer(sample_rate=SR)
    an.push(np.zeros((0, 2), dtype=np.float32))
    out = an.finalize()
    for value in out.values():
        assert math.isnan(value)


def test_band_split_push_equivalence() -> None:
    """Splitting input into chunks must give the same result as one push."""
    n = SR
    t = np.arange(n, dtype=np.float64) / SR
    left = (0.4 * np.sin(2.0 * np.pi * 200.0 * t)).astype(np.float32)
    right = (0.2 * np.sin(2.0 * np.pi * 200.0 * t)).astype(np.float32)

    single = BandImbalanceAccumulator(sample_rate=SR)
    single.push(left, right)

    split = BandImbalanceAccumulator(sample_rate=SR)
    for l_chunk, r_chunk in zip(np.array_split(left, 7), np.array_split(right, 7), strict=True):
        split.push(l_chunk, r_chunk)

    for band in Band:
        assert math.isclose(
            single.imbalance_db(band),
            split.imbalance_db(band),
            abs_tol=0.001,
        )
