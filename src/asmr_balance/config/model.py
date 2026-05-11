"""Top-level :class:`Config` — analysis parameters + rule thresholds.

Threshold subtrees live in :mod:`asmr_balance.rules.thresholds`; this model
composes them with the source / pipeline knobs.

All fields default to safe production values; users override via TOML
(:func:`asmr_balance.config.toml.load_config`) or CLI flags. The model is
``frozen``; CLI overrides produce a *new* :class:`Config` via
:meth:`Config.with_overrides`.
"""

from __future__ import annotations

from typing import Self

from pydantic import BaseModel, ConfigDict, Field

from asmr_balance.rules.thresholds import ThresholdSet
from asmr_balance.source.adt import LayoutPolicy


class Config(BaseModel):
    """The whole user-tunable configuration."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    # --- pipeline knobs --------------------------------------------------
    gate_lufs: float = -70.0
    """Absolute gate (LUFS) for :class:`IntegratedLoudnessReducer` (ADR-0007)."""

    layout_policy: LayoutPolicy = LayoutPolicy.DOWNMIX
    """How to fold non-stereo audio (ADR-0005)."""

    block_samples: int = 4800
    """PCM block size in samples (100 ms @ 48 kHz). The graph builder takes
    care of any other window size internally."""

    target_sample_rate: int | None = None
    """If set, all files are resampled to this rate before analysis (PyAV
    backend only). ``None`` means use the file's native rate."""

    workers: int = 0
    """File-level :class:`ProcessPoolExecutor` worker count. ``0`` ⇒
    ``os.cpu_count()``; ``1`` ⇒ fully sequential (no pool)."""

    # --- rule thresholds -------------------------------------------------
    thresholds: ThresholdSet = Field(default_factory=ThresholdSet)
    """All built-in rule thresholds, structured as a tree."""

    def with_overrides(
        self,
        *,
        gate_lufs: float | None = None,
        layout_policy: LayoutPolicy | None = None,
        workers: int | None = None,
    ) -> Self:
        """Return a new :class:`Config` with the supplied scalar overrides applied."""
        patch: dict[str, object] = {}
        if gate_lufs is not None:
            patch["gate_lufs"] = gate_lufs
        if layout_policy is not None:
            patch["layout_policy"] = layout_policy
        if workers is not None:
            patch["workers"] = workers
        if not patch:
            return self
        return self.model_copy(update=patch)
