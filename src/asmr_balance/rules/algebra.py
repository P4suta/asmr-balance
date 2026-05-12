"""Rule protocol, :class:`Flag` value type, and :func:`evaluate` fold."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, ClassVar, Protocol

from asmr_balance.algebra.semilattice import Verdict
from asmr_balance.metrics.record import MetricRecord, ScanStatus
from asmr_balance.rules.thresholds import ThresholdSet


@dataclass(frozen=True, slots=True)
class Flag:
    """A single rule firing.

    The rule that produced it knows its own ``code`` and constructs a Flag
    when its predicate triggers; consumers (sinks, CLI) display the code +
    severity + human-readable message.
    """

    code: str
    severity: Verdict
    message: str


@dataclass(frozen=True, slots=True)
class JudgeResult:
    """Aggregated outcome of :func:`evaluate` for one :class:`MetricRecord`."""

    flags: tuple[Flag, ...]
    verdict: Verdict


class Rule[M, T](Protocol):
    """A typed predicate-with-severity over a metric subtree and its thresholds.

    Implementing classes expose four attributes the dispatcher reads:

    * ``code`` — symbolic identifier emitted in :class:`Flag.code`. May be an
      instance attribute (e.g. :class:`BandBiasRule` parameterised by slot)
      rather than a :class:`typing.ClassVar`.
    * ``severity_ceiling`` — the maximum severity the rule can emit (used by
      tooling to summarize registries).
    * ``metric_path`` — name of the :class:`MetricRecord` attribute the rule
      consumes (e.g. ``"loudness"`` for :class:`LoudnessMetrics`).
    * ``threshold_path`` — name of the :class:`ThresholdSet` attribute the
      rule reads its thresholds from.

    The ``judge`` method returns either a :class:`Flag` (rule fired) or
    ``None`` (rule did not fire — Maybe pattern, distinct from
    ``Verdict.OK``).
    """

    code: str
    severity_ceiling: ClassVar[Verdict]
    metric_path: ClassVar[str]
    threshold_path: ClassVar[str]

    def judge(self, m: M, t: T) -> Flag | None: ...


type RuleSet = tuple[Rule[Any, Any], ...]
"""An ordered tuple of rules (order influences flag emission order, not severity)."""


def evaluate(rules: RuleSet, record: MetricRecord, thresholds: ThresholdSet) -> JudgeResult:
    """Apply every rule to the record and aggregate the verdict.

    Records with status other than :attr:`ScanStatus.ANALYZED` produce an
    empty flag tuple and a ``Verdict.OK`` verdict — the pipeline treats
    skipped / errored files as policy-neutral.
    """
    if record.status is not ScanStatus.ANALYZED:
        return JudgeResult(flags=(), verdict=Verdict.bottom())

    flags: list[Flag] = []
    verdict = Verdict.bottom()
    for rule in rules:
        subtree = getattr(record, rule.metric_path)
        if subtree is None:
            continue
        threshold = getattr(thresholds, rule.threshold_path)
        flag = rule.judge(subtree, threshold)
        if flag is None:
            continue
        flags.append(flag)
        verdict = verdict | flag.severity
    return JudgeResult(flags=tuple(flags), verdict=verdict)
