"""Pure-function flag judgement: ``MetricRecord × FlagThresholds → (flags, verdict)``.

All rules live here so that downstream consumers (TUI, HTML report, future
``inspect`` subcommand) get the same verdict from the same metrics.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from asmr_balance.types import Flag, MetricRecord, Verdict

if TYPE_CHECKING:
    from asmr_balance.config import FlagThresholds


def judge(metrics: MetricRecord, thresholds: FlagThresholds) -> tuple[list[Flag], Verdict]:
    """Compute all flags + the aggregate verdict for one ``MetricRecord``."""
    if metrics.skipped:
        return [], Verdict.OK

    flags: list[Flag] = []
    _gate_reject(metrics, flags)
    _lr_balance(metrics, thresholds, flags)
    _local_bias(metrics, thresholds, flags)
    _pseudo_mono(metrics, thresholds, flags)
    _phase_inv(metrics, thresholds, flags)
    _mid_side_narrow(metrics, thresholds, flags)
    _band_bias(metrics, thresholds, flags)

    if not flags:
        return flags, Verdict.OK
    verdict = max(_severity_rank(f.severity) for f in flags)
    return flags, _rank_severity(verdict)


_RANK = {Verdict.OK: 0, Verdict.WARN: 1, Verdict.FAIL: 2}
_INVERSE_RANK = {v: k for k, v in _RANK.items()}


def _severity_rank(verdict: Verdict) -> int:
    return _RANK[verdict]


def _rank_severity(rank: int) -> Verdict:
    return _INVERSE_RANK[rank]


def _gate_reject(metrics: MetricRecord, out: list[Flag]) -> None:
    bad_l = math.isinf(metrics.single_channel_lufs_l)
    bad_r = math.isinf(metrics.single_channel_lufs_r)
    if bad_l or bad_r:
        side = "L" if bad_l and not bad_r else "R" if bad_r and not bad_l else "both"
        out.append(
            Flag(
                code="GATE_REJECT_ALL",
                severity=Verdict.WARN,
                message=f"single-channel LUFS gated to -inf ({side})",
            )
        )


def _lr_balance(metrics: MetricRecord, thr: FlagThresholds, out: list[Flag]) -> None:
    if not math.isfinite(metrics.delta_lu):
        return
    abs_delta = abs(metrics.delta_lu)
    if abs_delta >= thr.lr_balance_fail_lu:
        out.append(
            Flag(
                code="LR_BALANCE_FAIL",
                severity=Verdict.FAIL,
                message=f"|ΔLU|={abs_delta:.2f} ≥ {thr.lr_balance_fail_lu}",
            )
        )
    elif abs_delta >= thr.lr_balance_warn_lu:
        out.append(
            Flag(
                code="LR_BALANCE_WARN",
                severity=Verdict.WARN,
                message=f"|ΔLU|={abs_delta:.2f} ≥ {thr.lr_balance_warn_lu}",
            )
        )


def _local_bias(metrics: MetricRecord, thr: FlagThresholds, out: list[Flag]) -> None:
    if math.isfinite(metrics.sliding_max_lu) and metrics.sliding_max_lu >= thr.local_bias_warn_lu:
        out.append(
            Flag(
                code="LOCAL_BIAS_WARN",
                severity=Verdict.WARN,
                message=f"sliding max ΔLU={metrics.sliding_max_lu:.2f}",
            )
        )
    if math.isfinite(metrics.sliding_p95_lu) and metrics.sliding_p95_lu >= thr.local_bias_fail_lu:
        out.append(
            Flag(
                code="LOCAL_BIAS_FAIL",
                severity=Verdict.FAIL,
                message=f"sliding p95 ΔLU={metrics.sliding_p95_lu:.2f}",
            )
        )


def _pseudo_mono(metrics: MetricRecord, thr: FlagThresholds, out: list[Flag]) -> None:
    if math.isfinite(metrics.pearson_r) and metrics.pearson_r >= thr.pseudo_mono_pearson:
        out.append(
            Flag(
                code="PSEUDO_MONO",
                severity=Verdict.WARN,
                message=f"Pearson r={metrics.pearson_r:.3f}",
            )
        )


def _phase_inv(metrics: MetricRecord, thr: FlagThresholds, out: list[Flag]) -> None:
    coh = metrics.low_phase_coherence
    if math.isfinite(coh) and coh < thr.phase_inv_warn:
        out.append(
            Flag(
                code="PHASE_INV_WARN",
                severity=Verdict.WARN,
                message=f"low-band coherence={metrics.low_phase_coherence:.3f}",
            )
        )


def _mid_side_narrow(metrics: MetricRecord, thr: FlagThresholds, out: list[Flag]) -> None:
    if math.isfinite(metrics.ms_ratio_db) and metrics.ms_ratio_db > thr.mid_side_narrow_db:
        out.append(
            Flag(
                code="MID_SIDE_NARROW",
                severity=Verdict.WARN,
                message=f"Mid/Side ratio={metrics.ms_ratio_db:.2f} dB",
            )
        )


def _band_bias(metrics: MetricRecord, thr: FlagThresholds, out: list[Flag]) -> None:
    for label, value in (
        ("low", metrics.band_imbalance_low),
        ("low_mid", metrics.band_imbalance_low_mid),
        ("high_mid", metrics.band_imbalance_high_mid),
        ("high", metrics.band_imbalance_high),
    ):
        if math.isfinite(value) and abs(value) >= thr.band_bias_db:
            out.append(
                Flag(
                    code=f"BAND_BIAS_{label.upper()}",
                    severity=Verdict.WARN,
                    message=f"{label} L/R imbalance={value:.2f} dB",
                )
            )
