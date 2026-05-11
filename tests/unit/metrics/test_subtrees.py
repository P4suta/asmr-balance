"""Smoke tests for typed metric subtrees."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from asmr_balance.metrics.subtrees import (
    BandImbalanceMetrics,
    DynamicsMetrics,
    LoudnessMetrics,
    LRAMetrics,
    PhaseMetrics,
    SlidingMetrics,
    StereoCorrelationMetrics,
)


def test_loudness_metrics_round_trips() -> None:
    m = LoudnessMetrics(
        lufs_i_stereo=-14.0,
        single_channel_lufs_l=-17.0,
        single_channel_lufs_r=-17.0,
        single_channel_lufs_ungated_l=-17.0,
        single_channel_lufs_ungated_r=-17.0,
        delta_lu=0.0,
        delta_lu_ungated=0.0,
    )
    assert m.lufs_i_stereo == -14.0


def test_loudness_metrics_is_frozen() -> None:
    m = LoudnessMetrics(
        lufs_i_stereo=-14.0,
        single_channel_lufs_l=-17.0,
        single_channel_lufs_r=-17.0,
        single_channel_lufs_ungated_l=-17.0,
        single_channel_lufs_ungated_r=-17.0,
        delta_lu=0.0,
        delta_lu_ungated=0.0,
    )
    with pytest.raises(ValidationError):
        m.lufs_i_stereo = -13.0  # type: ignore[misc]


def test_loudness_metrics_forbids_extra_fields() -> None:
    with pytest.raises(ValidationError):
        LoudnessMetrics(
            lufs_i_stereo=-14.0,
            single_channel_lufs_l=-17.0,
            single_channel_lufs_r=-17.0,
            single_channel_lufs_ungated_l=-17.0,
            single_channel_lufs_ungated_r=-17.0,
            delta_lu=0.0,
            delta_lu_ungated=0.0,
            mystery_field=0.0,  # type: ignore[call-arg]
        )


def test_band_imbalance_metrics_construct() -> None:
    m = BandImbalanceMetrics(
        low=0.0,
        low_mid=0.0,
        high_mid=0.0,
        high=0.0,
        third_octave={"b_1000hz": 0.5},
    )
    assert m.third_octave == {"b_1000hz": 0.5}


def test_lra_metrics_construct() -> None:
    assert LRAMetrics(lra_lu=8.5, max_short_term_lufs=-12.0).lra_lu == 8.5


def test_stereo_correlation_metrics_construct() -> None:
    m = StereoCorrelationMetrics(pearson_r=0.5, ms_ratio_db=3.0)
    assert m.pearson_r == 0.5


def test_sliding_metrics_construct() -> None:
    m = SlidingMetrics(max_lu=2.0, p95_lu=1.5, std_lu=0.5, t_max_sec=12.3)
    assert m.t_max_sec == 12.3


def test_phase_metrics_construct() -> None:
    assert PhaseMetrics(low_phase_coherence=-0.3).low_phase_coherence == -0.3


def test_dynamics_metrics_construct() -> None:
    m = DynamicsMetrics(
        true_peak_dbtp_l=-1.0,
        true_peak_dbtp_r=-1.2,
        true_peak_dbtp_max=-1.0,
        psr_db=15.0,
    )
    assert m.true_peak_dbtp_max == -1.0
