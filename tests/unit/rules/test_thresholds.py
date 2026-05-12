"""Tests for :mod:`asmr_balance.rules.thresholds`."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from asmr_balance.rules.thresholds import (
    LrBalanceThresholds,
    PseudoMonoThresholds,
    ThresholdSet,
)


def test_threshold_set_defaults() -> None:
    ts = ThresholdSet()
    assert ts.lr_balance.warn_lu == 3.0
    assert ts.lr_balance.fail_lu == 6.0
    assert ts.local_bias.warn_lu == 9.0
    assert ts.local_bias.fail_lu == 6.0
    assert ts.pseudo_mono.pearson_r == 0.95
    assert ts.phase_inv.coherence == -0.2
    assert ts.mid_side_narrow.db == 12.0
    assert ts.band_bias.db == 4.0
    assert ts.true_peak_clip.warn_dbtp == -1.0
    assert ts.true_peak_clip.fail_dbtp == 0.0


def test_threshold_subtree_is_frozen() -> None:
    t = LrBalanceThresholds()
    with pytest.raises(ValidationError):
        t.warn_lu = 2.0


def test_threshold_subtree_forbids_extra() -> None:
    with pytest.raises(ValidationError):
        PseudoMonoThresholds(pearson_r=0.5, mystery=1)  # type: ignore[call-arg]


def test_threshold_set_partial_override() -> None:
    ts = ThresholdSet(lr_balance=LrBalanceThresholds(warn_lu=1.0, fail_lu=2.0))
    assert ts.lr_balance.warn_lu == 1.0
    assert ts.lr_balance.fail_lu == 2.0
    assert ts.local_bias.warn_lu == 9.0  # unchanged
