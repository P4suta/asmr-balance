"""Tests for :mod:`asmr_balance.config`."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from asmr_balance.config.model import Config
from asmr_balance.config.toml import load_config
from asmr_balance.source.adt import LayoutPolicy


def test_default_config_values() -> None:
    cfg = Config()
    assert cfg.gate_lufs == -70.0
    assert cfg.layout_policy is LayoutPolicy.DOWNMIX
    assert cfg.workers == 0
    assert cfg.block_duration_sec == 0.1
    assert cfg.target_sample_rate is None
    assert cfg.thresholds.lr_balance.warn_lu == 3.0


def test_config_is_frozen() -> None:
    cfg = Config()
    with pytest.raises(ValidationError):
        cfg.gate_lufs = -60.0  # type: ignore[misc]


def test_config_forbids_extra_fields() -> None:
    with pytest.raises(ValidationError):
        Config(mystery_field=1)  # type: ignore[call-arg]


def test_with_overrides_returns_new_instance() -> None:
    cfg = Config()
    new = cfg.with_overrides(gate_lufs=-60.0)
    assert cfg.gate_lufs == -70.0
    assert new.gate_lufs == -60.0
    assert new is not cfg


def test_with_overrides_noop_returns_self() -> None:
    cfg = Config()
    assert cfg.with_overrides() is cfg


def test_with_overrides_layout_policy() -> None:
    cfg = Config()
    new = cfg.with_overrides(layout_policy=LayoutPolicy.SKIP)
    assert new.layout_policy is LayoutPolicy.SKIP


def test_load_toml_minimal(tmp_path: Path) -> None:
    p = tmp_path / "cfg.toml"
    p.write_text("gate_lufs = -60.0\nworkers = 4\n")
    cfg = load_config(p)
    assert cfg.gate_lufs == -60.0
    assert cfg.workers == 4


def test_load_toml_nested_thresholds(tmp_path: Path) -> None:
    p = tmp_path / "cfg.toml"
    p.write_text(
        "[thresholds.lr_balance]\nwarn_lu = 1.0\nfail_lu = 2.0\n"
        "[thresholds.true_peak_clip]\nfail_dbtp = -0.5\n"
    )
    cfg = load_config(p)
    assert cfg.thresholds.lr_balance.warn_lu == 1.0
    assert cfg.thresholds.lr_balance.fail_lu == 2.0
    assert cfg.thresholds.true_peak_clip.fail_dbtp == -0.5
    # untouched defaults preserved
    assert cfg.thresholds.local_bias.warn_lu == 9.0


def test_load_toml_rejects_unknown_top_level_key(tmp_path: Path) -> None:
    p = tmp_path / "cfg.toml"
    p.write_text("unknown_key = 1\n")
    with pytest.raises(ValidationError):
        load_config(p)


def test_load_toml_rejects_unknown_threshold_key(tmp_path: Path) -> None:
    p = tmp_path / "cfg.toml"
    p.write_text("[thresholds.lr_balance]\nmystery = 1.0\n")
    with pytest.raises(ValidationError):
        load_config(p)
