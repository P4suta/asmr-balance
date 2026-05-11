"""Configuration types loaded from TOML (or built from defaults / CLI flags).

Threshold values live here so they can be tuned per project from a single TOML
file rather than rebuilding the package (ADR-0007, ADR-0008).
"""

from __future__ import annotations

import tomllib
from enum import StrEnum
from typing import TYPE_CHECKING, Any, Self

from pydantic import BaseModel, ConfigDict, Field

if TYPE_CHECKING:
    from pathlib import Path


class LayoutPolicy(StrEnum):
    """How to handle non-stereo audio (ADR-0005)."""

    FL_FR = "fl-fr"
    DOWNMIX = "downmix"
    SKIP = "skip"


class FlagThresholds(BaseModel):
    """All flag thresholds; override via CLI or TOML."""

    model_config = ConfigDict(frozen=True)

    lr_balance_warn_lu: float = 3.0
    lr_balance_fail_lu: float = 6.0
    local_bias_warn_lu: float = 9.0
    local_bias_fail_lu: float = 6.0
    pseudo_mono_pearson: float = 0.95
    phase_inv_warn: float = -0.2
    mid_side_narrow_db: float = 12.0
    band_bias_db: float = 4.0


class Config(BaseModel):
    """Top-level user-tunable configuration."""

    model_config = ConfigDict(frozen=True)

    gate_lufs: float = -70.0
    layout_policy: LayoutPolicy = LayoutPolicy.DOWNMIX
    workers: int = 0  # ``0`` ⇒ ``os.cpu_count()`` at the pipeline boundary
    flag_thresholds: FlagThresholds = Field(default_factory=FlagThresholds)
    block_samples: int = 4800  # one 100 ms hop @ 48 kHz; resized at decode time

    @classmethod
    def from_toml(cls, path: Path) -> Self:
        """Load a config from a TOML file (top-level keys map to fields)."""
        with path.open("rb") as fp:
            data = tomllib.load(fp)
        thresholds = data.pop("flag_thresholds", None)
        kwargs: dict[str, Any] = dict(data)
        if thresholds is not None:
            kwargs["flag_thresholds"] = FlagThresholds(**thresholds)
        return cls(**kwargs)
