"""Per-rule threshold subtrees.

Threshold subtrees are *owned by the rules* — there is no flat
``FlagThresholds`` model with eight loose floats anymore. Adding a new rule
means defining its threshold subtree here and registering it on
:class:`ThresholdSet`.

All subtrees are frozen pydantic models so they're safe to ship across
:class:`concurrent.futures.ProcessPoolExecutor` boundaries.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class GateRejectThresholds(_Frozen):
    """No tunables — :class:`GateRejectRule` fires when a side is ``-inf``."""


class LrBalanceThresholds(_Frozen):
    """Integrated L/R loudness imbalance thresholds in LU."""

    warn_lu: float = 3.0
    fail_lu: float = 6.0


class LocalBiasThresholds(_Frozen):
    """Per-block ΔLU thresholds.

    ``warn_lu`` is checked against the *max* (single-block spike) and
    ``fail_lu`` against the *p95* (sustained imbalance). The asymmetric
    quantile is intentional: a sustained imbalance is more serious than a
    single momentary spike, so the fail threshold can be lower than warn.
    """

    warn_lu: float = 9.0
    fail_lu: float = 6.0


class PseudoMonoThresholds(_Frozen):
    """Pearson L/R correlation threshold above which a mix is "pseudo-mono"."""

    pearson_r: float = 0.95


class PhaseInvThresholds(_Frozen):
    """Low-band coherence below which we suspect phase inversion (LU)."""

    coherence: float = -0.2


class MidSideNarrowThresholds(_Frozen):
    """Mid/Side energy ratio above which the side image is dangerously narrow (dB)."""

    db: float = 12.0


class BandBiasThresholds(_Frozen):
    """Per-band L/R imbalance threshold (dB), applied to each 4-band aggregate."""

    db: float = 4.0


class TruePeakClipThresholds(_Frozen):
    """Inter-sample-peak limits (dBTP).

    ``warn_dbtp``: spec-recommended ceiling for streaming masters (e.g. EBU
    R128 ``-1 dBTP``).
    ``fail_dbtp``: hard clip — peak ``≥ 0 dBTP`` means inter-sample clipping
    is unavoidable on consumer DACs.
    """

    warn_dbtp: float = -1.0
    fail_dbtp: float = 0.0


class ThresholdSet(_Frozen):
    """The full rule threshold forest, one subtree per rule (group)."""

    gate_reject: GateRejectThresholds = Field(default_factory=GateRejectThresholds)
    lr_balance: LrBalanceThresholds = Field(default_factory=LrBalanceThresholds)
    local_bias: LocalBiasThresholds = Field(default_factory=LocalBiasThresholds)
    pseudo_mono: PseudoMonoThresholds = Field(default_factory=PseudoMonoThresholds)
    phase_inv: PhaseInvThresholds = Field(default_factory=PhaseInvThresholds)
    mid_side_narrow: MidSideNarrowThresholds = Field(default_factory=MidSideNarrowThresholds)
    band_bias: BandBiasThresholds = Field(default_factory=BandBiasThresholds)
    true_peak_clip: TruePeakClipThresholds = Field(default_factory=TruePeakClipThresholds)
