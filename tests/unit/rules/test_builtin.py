"""Tests for built-in rules."""

from __future__ import annotations

import math

import pytest

from asmr_balance.algebra.semilattice import Verdict
from asmr_balance.metrics.subtrees import (
    BandImbalanceMetrics,
    DynamicsMetrics,
    LoudnessMetrics,
    PhaseMetrics,
    SlidingMetrics,
    StereoCorrelationMetrics,
)
from asmr_balance.rules.builtin import (
    BandBiasRule,
    GateRejectRule,
    LocalBiasRule,
    LrBalanceRule,
    MidSideNarrowRule,
    PhaseInvRule,
    PseudoMonoRule,
    TruePeakClipRule,
)
from asmr_balance.rules.thresholds import (
    BandBiasThresholds,
    GateRejectThresholds,
    LocalBiasThresholds,
    LrBalanceThresholds,
    MidSideNarrowThresholds,
    PhaseInvThresholds,
    PseudoMonoThresholds,
    TruePeakClipThresholds,
)


def _loud(*, delta_lu: float = 0.0, sc_l: float = -17.0, sc_r: float = -17.0) -> LoudnessMetrics:
    return LoudnessMetrics(
        lufs_i_stereo=-14.0,
        single_channel_lufs_l=sc_l,
        single_channel_lufs_r=sc_r,
        single_channel_lufs_ungated_l=sc_l,
        single_channel_lufs_ungated_r=sc_r,
        delta_lu=delta_lu,
        delta_lu_ungated=delta_lu,
    )


# --- GateRejectRule ---------------------------------------------------------


def test_gate_reject_fires_when_one_side_inf() -> None:
    rule = GateRejectRule()
    f = rule.judge(_loud(sc_l=-17.0, sc_r=float("-inf")), GateRejectThresholds())
    assert f is not None
    assert f.code == "GATE_REJECT_ALL"
    assert f.severity is Verdict.WARN
    assert "R" in f.message


def test_gate_reject_silent_when_finite() -> None:
    rule = GateRejectRule()
    assert rule.judge(_loud(sc_l=-17.0, sc_r=-17.0), GateRejectThresholds()) is None


def test_gate_reject_says_both_when_both_inf() -> None:
    rule = GateRejectRule()
    f = rule.judge(_loud(sc_l=float("-inf"), sc_r=float("-inf")), GateRejectThresholds())
    assert f is not None
    assert "both" in f.message


# --- LrBalanceRule ----------------------------------------------------------


def test_lr_balance_fails_above_fail_lu() -> None:
    rule = LrBalanceRule()
    f = rule.judge(_loud(delta_lu=7.0), LrBalanceThresholds(warn_lu=3.0, fail_lu=6.0))
    assert f is not None
    assert f.severity is Verdict.FAIL
    assert f.code == "LR_BALANCE_FAIL"


def test_lr_balance_warns_between_warn_and_fail() -> None:
    rule = LrBalanceRule()
    f = rule.judge(_loud(delta_lu=-4.0), LrBalanceThresholds(warn_lu=3.0, fail_lu=6.0))
    assert f is not None
    assert f.severity is Verdict.WARN
    assert f.code == "LR_BALANCE_WARN"


def test_lr_balance_quiet_below_warn() -> None:
    rule = LrBalanceRule()
    assert rule.judge(_loud(delta_lu=1.0), LrBalanceThresholds()) is None


def test_lr_balance_silent_when_nan() -> None:
    rule = LrBalanceRule()
    assert rule.judge(_loud(delta_lu=float("nan")), LrBalanceThresholds()) is None


# --- LocalBiasRule ----------------------------------------------------------


def test_local_bias_fails_on_p95() -> None:
    rule = LocalBiasRule()
    m = SlidingMetrics(max_lu=2.0, p95_lu=7.0, std_lu=1.0, t_max_sec=0.0)
    f = rule.judge(m, LocalBiasThresholds())
    assert f is not None
    assert f.severity is Verdict.FAIL


def test_local_bias_warns_on_max_only() -> None:
    rule = LocalBiasRule()
    m = SlidingMetrics(max_lu=12.0, p95_lu=1.0, std_lu=0.5, t_max_sec=0.0)
    f = rule.judge(m, LocalBiasThresholds())
    assert f is not None
    assert f.severity is Verdict.WARN


def test_local_bias_silent_below_thresholds() -> None:
    rule = LocalBiasRule()
    m = SlidingMetrics(max_lu=1.0, p95_lu=0.5, std_lu=0.1, t_max_sec=0.0)
    assert rule.judge(m, LocalBiasThresholds()) is None


# --- PseudoMonoRule ---------------------------------------------------------


def test_pseudo_mono_warns_at_high_pearson() -> None:
    rule = PseudoMonoRule()
    m = StereoCorrelationMetrics(pearson_r=0.97, ms_ratio_db=0.0)
    f = rule.judge(m, PseudoMonoThresholds(pearson_r=0.95))
    assert f is not None
    assert f.severity is Verdict.WARN


def test_pseudo_mono_silent_below() -> None:
    rule = PseudoMonoRule()
    m = StereoCorrelationMetrics(pearson_r=0.5, ms_ratio_db=0.0)
    assert rule.judge(m, PseudoMonoThresholds()) is None


def test_pseudo_mono_silent_on_nan() -> None:
    rule = PseudoMonoRule()
    m = StereoCorrelationMetrics(pearson_r=float("nan"), ms_ratio_db=0.0)
    assert rule.judge(m, PseudoMonoThresholds()) is None


# --- PhaseInvRule -----------------------------------------------------------


def test_phase_inv_warns_below_threshold() -> None:
    rule = PhaseInvRule()
    f = rule.judge(PhaseMetrics(low_phase_coherence=-0.5), PhaseInvThresholds())
    assert f is not None
    assert f.severity is Verdict.WARN


def test_phase_inv_silent_above_threshold() -> None:
    rule = PhaseInvRule()
    assert rule.judge(PhaseMetrics(low_phase_coherence=0.5), PhaseInvThresholds()) is None


# --- MidSideNarrowRule ------------------------------------------------------


def test_mid_side_narrow_warns_at_high_ratio() -> None:
    rule = MidSideNarrowRule()
    m = StereoCorrelationMetrics(pearson_r=0.0, ms_ratio_db=15.0)
    f = rule.judge(m, MidSideNarrowThresholds(db=12.0))
    assert f is not None
    assert f.severity is Verdict.WARN


def test_mid_side_narrow_silent_below() -> None:
    rule = MidSideNarrowRule()
    m = StereoCorrelationMetrics(pearson_r=0.0, ms_ratio_db=5.0)
    assert rule.judge(m, MidSideNarrowThresholds(db=12.0)) is None


# --- BandBiasRule -----------------------------------------------------------


def _band(
    low: float = 0.0, low_mid: float = 0.0, high_mid: float = 0.0, high: float = 0.0
) -> BandImbalanceMetrics:
    return BandImbalanceMetrics(
        low=low, low_mid=low_mid, high_mid=high_mid, high=high, third_octave={}
    )


@pytest.mark.parametrize("slot", ["low", "low_mid", "high_mid", "high"])
def test_band_bias_per_slot_fires(slot: str) -> None:
    rule = BandBiasRule(slot=slot)
    kwargs = {slot: 5.0}
    m = _band(**kwargs)
    f = rule.judge(m, BandBiasThresholds(db=4.0))
    assert f is not None
    assert f.code == f"BAND_BIAS_{slot.upper()}"
    assert f.severity is Verdict.WARN


def test_band_bias_silent_below_threshold() -> None:
    rule = BandBiasRule(slot="low")
    assert rule.judge(_band(low=2.0), BandBiasThresholds(db=4.0)) is None


def test_band_bias_silent_on_nan() -> None:
    rule = BandBiasRule(slot="low")
    assert rule.judge(_band(low=math.nan), BandBiasThresholds(db=4.0)) is None


# --- TruePeakClipRule -------------------------------------------------------


def _dyn(dbtp_max: float) -> DynamicsMetrics:
    return DynamicsMetrics(
        true_peak_dbtp_l=dbtp_max,
        true_peak_dbtp_r=dbtp_max - 1.0,
        true_peak_dbtp_max=dbtp_max,
        psr_db=10.0,
    )


def test_true_peak_fails_at_0_dbtp() -> None:
    rule = TruePeakClipRule()
    f = rule.judge(_dyn(0.5), TruePeakClipThresholds())
    assert f is not None
    assert f.severity is Verdict.FAIL


def test_true_peak_warns_at_minus_1_dbtp() -> None:
    rule = TruePeakClipRule()
    f = rule.judge(_dyn(-0.5), TruePeakClipThresholds())
    assert f is not None
    assert f.severity is Verdict.WARN


def test_true_peak_silent_well_below() -> None:
    rule = TruePeakClipRule()
    assert rule.judge(_dyn(-10.0), TruePeakClipThresholds()) is None


def test_true_peak_silent_on_neg_inf() -> None:
    rule = TruePeakClipRule()
    assert rule.judge(_dyn(float("-inf")), TruePeakClipThresholds()) is None
