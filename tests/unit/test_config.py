"""Tests for ``asmr_balance.config``."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from asmr_balance.config import Config, FlagThresholds, LayoutPolicy

if TYPE_CHECKING:
    from pathlib import Path


def test_default_thresholds_have_expected_values() -> None:
    thr = FlagThresholds()
    assert thr.lr_balance_warn_lu == 3.0
    assert thr.lr_balance_fail_lu == 6.0


def test_default_config_uses_downmix_policy_and_spec_gate() -> None:
    cfg = Config()
    assert cfg.layout_policy is LayoutPolicy.DOWNMIX
    assert cfg.gate_lufs == -70.0


def test_from_toml_minimal(tmp_path: Path) -> None:
    toml = tmp_path / "c.toml"
    toml.write_text('gate_lufs = -90.0\nlayout_policy = "fl-fr"\n', encoding="utf-8")
    cfg = Config.from_toml(toml)
    assert cfg.gate_lufs == -90.0
    assert cfg.layout_policy is LayoutPolicy.FL_FR


def test_from_toml_with_thresholds(tmp_path: Path) -> None:
    toml = tmp_path / "c.toml"
    toml.write_text(
        "[flag_thresholds]\nlr_balance_fail_lu = 9.0\nband_bias_db = 5.5\n",
        encoding="utf-8",
    )
    cfg = Config.from_toml(toml)
    assert cfg.flag_thresholds.lr_balance_fail_lu == 9.0
    assert cfg.flag_thresholds.band_bias_db == 5.5


def test_from_toml_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        Config.from_toml(tmp_path / "nope.toml")
