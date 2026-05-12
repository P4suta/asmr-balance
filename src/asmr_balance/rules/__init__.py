r"""Rule algebra: typed predicate-with-severity registry.

Each :class:`Rule` is a typed predicate :math:`M \\times T \\to Flag \\cup \\{\\bot\\}`
where ``M`` is a metric subtree (e.g. :class:`LoudnessMetrics`) and ``T`` is
the matching threshold subtree (e.g. :class:`LrBalanceThresholds`). Returning
``None`` indicates the rule did not fire — distinct from
``Verdict.OK`` which would mean the rule actively certified the metric.

A :data:`RuleSet` is a tuple of rules. :func:`evaluate` folds them over a
:class:`MetricRecord` and aggregates per-rule severities into a single
:class:`Verdict` via the bounded join-semilattice ``OK ⊑ WARN ⊑ FAIL``.
"""

from __future__ import annotations

from asmr_balance.rules.algebra import Flag, JudgeResult, Rule, RuleSet, evaluate
from asmr_balance.rules.builtin import (
    DEFAULT_RULES,
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
    ThresholdSet,
    TruePeakClipThresholds,
)

__all__ = [
    "DEFAULT_RULES",
    "BandBiasRule",
    "BandBiasThresholds",
    "Flag",
    "GateRejectRule",
    "GateRejectThresholds",
    "JudgeResult",
    "LocalBiasRule",
    "LocalBiasThresholds",
    "LrBalanceRule",
    "LrBalanceThresholds",
    "MidSideNarrowRule",
    "MidSideNarrowThresholds",
    "PhaseInvRule",
    "PhaseInvThresholds",
    "PseudoMonoRule",
    "PseudoMonoThresholds",
    "Rule",
    "RuleSet",
    "ThresholdSet",
    "TruePeakClipRule",
    "TruePeakClipThresholds",
    "evaluate",
]
