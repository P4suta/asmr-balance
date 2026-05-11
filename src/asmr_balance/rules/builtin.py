"""Built-in rules + :data:`DEFAULT_RULES` registry.

Each rule is a tiny dataclass (or stateless class) with a ``judge`` method
that returns ``Flag | None``. The :data:`DEFAULT_RULES` tuple is the order
the pipeline applies them; adding a rule means adding one class here, one
field on :class:`~asmr_balance.rules.thresholds.ThresholdSet`, and one entry
in :data:`DEFAULT_RULES`.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import ClassVar

from asmr_balance.algebra.semilattice import Verdict
from asmr_balance.metrics.subtrees import (
    BandImbalanceMetrics,
    DynamicsMetrics,
    LoudnessMetrics,
    PhaseMetrics,
    SlidingMetrics,
    StereoCorrelationMetrics,
)
from asmr_balance.rules.algebra import Flag, RuleSet
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


# ---------------------------------------------------------------------------
# Gate-reject — at least one side lost all blocks to the absolute gate.
# ---------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class GateRejectRule:
    code: str = "GATE_REJECT_ALL"
    severity_ceiling: ClassVar[Verdict] = Verdict.WARN
    metric_path: ClassVar[str] = "loudness"
    threshold_path: ClassVar[str] = "gate_reject"

    def judge(self, m: LoudnessMetrics, t: GateRejectThresholds) -> Flag | None:  # noqa: ARG002
        bad_l = math.isinf(m.single_channel_lufs_l)
        bad_r = math.isinf(m.single_channel_lufs_r)
        if not (bad_l or bad_r):
            return None
        side = "L" if bad_l and not bad_r else "R" if bad_r and not bad_l else "both"
        return Flag(
            code=self.code,
            severity=Verdict.WARN,
            message=f"single-channel LUFS gated to -inf ({side})",
        )


# ---------------------------------------------------------------------------
# Integrated L/R imbalance — symmetric warn/fail thresholds.
# ---------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class LrBalanceRule:
    code: str = "LR_BALANCE"
    severity_ceiling: ClassVar[Verdict] = Verdict.FAIL
    metric_path: ClassVar[str] = "loudness"
    threshold_path: ClassVar[str] = "lr_balance"

    def judge(self, m: LoudnessMetrics, t: LrBalanceThresholds) -> Flag | None:
        if not math.isfinite(m.delta_lu):
            return None
        abs_delta = abs(m.delta_lu)
        if abs_delta >= t.fail_lu:
            return Flag(
                code=f"{self.code}_FAIL",
                severity=Verdict.FAIL,
                message=f"|ΔLU|={abs_delta:.2f} ≥ {t.fail_lu}",
            )
        if abs_delta >= t.warn_lu:
            return Flag(
                code=f"{self.code}_WARN",
                severity=Verdict.WARN,
                message=f"|ΔLU|={abs_delta:.2f} ≥ {t.warn_lu}",
            )
        return None


# ---------------------------------------------------------------------------
# Local imbalance over sliding windows.
# warn ← max (spike); fail ← p95 (sustained).
# ---------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class LocalBiasRule:
    code: str = "LOCAL_BIAS"
    severity_ceiling: ClassVar[Verdict] = Verdict.FAIL
    metric_path: ClassVar[str] = "sliding"
    threshold_path: ClassVar[str] = "local_bias"

    def judge(self, m: SlidingMetrics, t: LocalBiasThresholds) -> Flag | None:
        if math.isfinite(m.p95_lu) and m.p95_lu >= t.fail_lu:
            return Flag(
                code=f"{self.code}_FAIL",
                severity=Verdict.FAIL,
                message=f"sliding p95 ΔLU={m.p95_lu:.2f}",
            )
        if math.isfinite(m.max_lu) and m.max_lu >= t.warn_lu:
            return Flag(
                code=f"{self.code}_WARN",
                severity=Verdict.WARN,
                message=f"sliding max ΔLU={m.max_lu:.2f}",
            )
        return None


# ---------------------------------------------------------------------------
# Pseudo-mono — Pearson too high.
# ---------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class PseudoMonoRule:
    code: str = "PSEUDO_MONO"
    severity_ceiling: ClassVar[Verdict] = Verdict.WARN
    metric_path: ClassVar[str] = "correlation"
    threshold_path: ClassVar[str] = "pseudo_mono"

    def judge(self, m: StereoCorrelationMetrics, t: PseudoMonoThresholds) -> Flag | None:
        if math.isfinite(m.pearson_r) and m.pearson_r >= t.pearson_r:
            return Flag(
                code=self.code,
                severity=Verdict.WARN,
                message=f"Pearson r={m.pearson_r:.3f}",
            )
        return None


# ---------------------------------------------------------------------------
# Phase inversion in low band.
# ---------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class PhaseInvRule:
    code: str = "PHASE_INV_WARN"
    severity_ceiling: ClassVar[Verdict] = Verdict.WARN
    metric_path: ClassVar[str] = "phase"
    threshold_path: ClassVar[str] = "phase_inv"

    def judge(self, m: PhaseMetrics, t: PhaseInvThresholds) -> Flag | None:
        coh = m.low_phase_coherence
        if math.isfinite(coh) and coh < t.coherence:
            return Flag(
                code=self.code,
                severity=Verdict.WARN,
                message=f"low-band coherence={coh:.3f}",
            )
        return None


# ---------------------------------------------------------------------------
# Mid/Side imbalance (narrow side image).
# ---------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class MidSideNarrowRule:
    code: str = "MID_SIDE_NARROW"
    severity_ceiling: ClassVar[Verdict] = Verdict.WARN
    metric_path: ClassVar[str] = "correlation"
    threshold_path: ClassVar[str] = "mid_side_narrow"

    def judge(self, m: StereoCorrelationMetrics, t: MidSideNarrowThresholds) -> Flag | None:
        if math.isfinite(m.ms_ratio_db) and m.ms_ratio_db > t.db:
            return Flag(
                code=self.code,
                severity=Verdict.WARN,
                message=f"Mid/Side ratio={m.ms_ratio_db:.2f} dB",
            )
        return None


# ---------------------------------------------------------------------------
# Per-band imbalance — one rule instance per 4-band slot.
# ---------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class BandBiasRule:
    slot: str  # "low" | "low_mid" | "high_mid" | "high"
    severity_ceiling: ClassVar[Verdict] = Verdict.WARN
    metric_path: ClassVar[str] = "band"
    threshold_path: ClassVar[str] = "band_bias"

    @property
    def code(self) -> str:
        return f"BAND_BIAS_{self.slot.upper()}"

    def judge(self, m: BandImbalanceMetrics, t: BandBiasThresholds) -> Flag | None:
        value: float = getattr(m, self.slot)
        if math.isfinite(value) and abs(value) >= t.db:
            return Flag(
                code=self.code,
                severity=Verdict.WARN,
                message=f"{self.slot} L/R imbalance={value:.2f} dB",
            )
        return None


# ---------------------------------------------------------------------------
# True-peak / inter-sample clipping.
# ---------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class TruePeakClipRule:
    code: str = "TRUE_PEAK"
    severity_ceiling: ClassVar[Verdict] = Verdict.FAIL
    metric_path: ClassVar[str] = "dynamics"
    threshold_path: ClassVar[str] = "true_peak_clip"

    def judge(self, m: DynamicsMetrics, t: TruePeakClipThresholds) -> Flag | None:
        dbtp = m.true_peak_dbtp_max
        if not math.isfinite(dbtp):
            return None
        if dbtp >= t.fail_dbtp:
            return Flag(
                code=f"{self.code}_FAIL",
                severity=Verdict.FAIL,
                message=f"true peak {dbtp:.2f} dBTP ≥ {t.fail_dbtp} (clipping)",
            )
        if dbtp >= t.warn_dbtp:
            return Flag(
                code=f"{self.code}_WARN",
                severity=Verdict.WARN,
                message=f"true peak {dbtp:.2f} dBTP ≥ {t.warn_dbtp}",
            )
        return None


# ---------------------------------------------------------------------------
# Default registry — order influences flag emission order in reports.
# ---------------------------------------------------------------------------
DEFAULT_RULES: RuleSet = (
    GateRejectRule(),
    LrBalanceRule(),
    LocalBiasRule(),
    PseudoMonoRule(),
    PhaseInvRule(),
    MidSideNarrowRule(),
    BandBiasRule(slot="low"),
    BandBiasRule(slot="low_mid"),
    BandBiasRule(slot="high_mid"),
    BandBiasRule(slot="high"),
    TruePeakClipRule(),
)
