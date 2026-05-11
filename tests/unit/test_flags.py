"""Tests for ``asmr_balance.flags.judge``."""

from __future__ import annotations

from pathlib import Path

from asmr_balance.config import FlagThresholds
from asmr_balance.flags import judge
from asmr_balance.types import MetricRecord, Verdict

_THR = FlagThresholds()


def _make(**overrides: float | str | bool | None) -> MetricRecord:
    defaults: dict[str, object] = {
        "file_path": Path("/tmp/x.wav"),
        "sample_rate": 48000,
        "duration_sec": 5.0,
        "channel_layout": "stereo",
    }
    defaults.update(overrides)
    return MetricRecord(**defaults)  # type: ignore[arg-type]


def test_judge_skipped_returns_empty() -> None:
    rec = _make(skipped=True, skip_reason="mono")
    flags, verdict = judge(rec, _THR)
    assert flags == []
    assert verdict is Verdict.OK


def test_judge_ok_signal_has_no_flags() -> None:
    rec = _make(
        single_channel_lufs_l=-20.0,
        single_channel_lufs_r=-20.5,
        delta_lu=0.5,
        pearson_r=0.5,
        ms_ratio_db=1.0,
    )
    flags, verdict = judge(rec, _THR)
    assert flags == []
    assert verdict is Verdict.OK


def test_judge_lr_balance_warn() -> None:
    rec = _make(
        single_channel_lufs_l=-15.0,
        single_channel_lufs_r=-18.5,
        delta_lu=3.5,
    )
    flags, verdict = judge(rec, _THR)
    codes = {f.code for f in flags}
    assert "LR_BALANCE_WARN" in codes
    assert verdict is Verdict.WARN


def test_judge_lr_balance_fail() -> None:
    rec = _make(
        single_channel_lufs_l=-15.0,
        single_channel_lufs_r=-25.0,
        delta_lu=10.0,
    )
    flags, verdict = judge(rec, _THR)
    codes = {f.code for f in flags}
    assert "LR_BALANCE_FAIL" in codes
    assert verdict is Verdict.FAIL


def test_judge_gate_reject_left() -> None:
    rec = _make(
        single_channel_lufs_l=float("-inf"),
        single_channel_lufs_r=-20.0,
    )
    flags, _ = judge(rec, _THR)
    assert any(f.code == "GATE_REJECT_ALL" and "L" in f.message for f in flags)


def test_judge_gate_reject_right() -> None:
    rec = _make(
        single_channel_lufs_l=-20.0,
        single_channel_lufs_r=float("-inf"),
    )
    flags, _ = judge(rec, _THR)
    assert any(f.code == "GATE_REJECT_ALL" and "R" in f.message for f in flags)


def test_judge_gate_reject_both() -> None:
    rec = _make(
        single_channel_lufs_l=float("-inf"),
        single_channel_lufs_r=float("-inf"),
    )
    flags, _ = judge(rec, _THR)
    assert any(f.code == "GATE_REJECT_ALL" and "both" in f.message for f in flags)


def test_judge_pseudo_mono() -> None:
    rec = _make(pearson_r=0.99, single_channel_lufs_l=-20.0, single_channel_lufs_r=-20.0)
    flags, verdict = judge(rec, _THR)
    assert any(f.code == "PSEUDO_MONO" for f in flags)
    assert verdict is Verdict.WARN


def test_judge_phase_inv() -> None:
    rec = _make(low_phase_coherence=-0.5, single_channel_lufs_l=-20.0, single_channel_lufs_r=-20.0)
    flags, _ = judge(rec, _THR)
    assert any(f.code == "PHASE_INV_WARN" for f in flags)


def test_judge_mid_side_narrow() -> None:
    rec = _make(ms_ratio_db=15.0, single_channel_lufs_l=-20.0, single_channel_lufs_r=-20.0)
    flags, _ = judge(rec, _THR)
    assert any(f.code == "MID_SIDE_NARROW" for f in flags)


def test_judge_local_bias_warn() -> None:
    rec = _make(
        sliding_max_lu=12.0,
        sliding_p95_lu=1.0,
        single_channel_lufs_l=-20.0,
        single_channel_lufs_r=-20.0,
    )
    flags, _ = judge(rec, _THR)
    codes = {f.code for f in flags}
    assert "LOCAL_BIAS_WARN" in codes


def test_judge_local_bias_fail() -> None:
    rec = _make(
        sliding_max_lu=2.0,
        sliding_p95_lu=7.0,
        single_channel_lufs_l=-20.0,
        single_channel_lufs_r=-20.0,
    )
    flags, verdict = judge(rec, _THR)
    codes = {f.code for f in flags}
    assert "LOCAL_BIAS_FAIL" in codes
    assert verdict is Verdict.FAIL


def test_judge_band_bias_all_bands_fire() -> None:
    rec = _make(
        single_channel_lufs_l=-20.0,
        single_channel_lufs_r=-20.0,
        band_imbalance_low=5.0,
        band_imbalance_low_mid=-5.0,
        band_imbalance_high_mid=4.5,
        band_imbalance_high=-4.5,
    )
    flags, _ = judge(rec, _THR)
    codes = {f.code for f in flags}
    assert codes.issuperset(
        {
            "BAND_BIAS_LOW",
            "BAND_BIAS_LOW_MID",
            "BAND_BIAS_HIGH_MID",
            "BAND_BIAS_HIGH",
        }
    )


def test_judge_lr_balance_nan_does_not_flag() -> None:
    rec = _make(
        single_channel_lufs_l=-20.0,
        single_channel_lufs_r=-20.0,
        delta_lu=float("nan"),
    )
    flags, _ = judge(rec, _THR)
    codes = {f.code for f in flags}
    assert "LR_BALANCE_WARN" not in codes
    assert "LR_BALANCE_FAIL" not in codes
