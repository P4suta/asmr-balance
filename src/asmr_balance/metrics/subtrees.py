"""Typed subtrees emitted by reducers.

Every :class:`~asmr_balance.algebra.reducer.Reducer` finalises into one of the
classes below. The :class:`~asmr_balance.metrics.record.MetricRecord` is a
forest of these subtrees plus a :class:`~asmr_balance.metrics.record.FileMeta`
root.

Subtree fields use scalar :class:`float` exclusively so that the entire record
projects cleanly to a flat parquet schema via dotted-flatten naming (see
:mod:`asmr_balance.sink.parquet`). The only non-scalar field is
:attr:`BandImbalanceMetrics.third_octave`, which is a 31-key mapping derived
from :data:`asmr_balance.nodes.bandsplit.BANDS`.

All models are pydantic ``frozen`` for safe sharing across process boundaries.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class _Frozen(BaseModel):
    """Base for frozen metric subtrees. Forbids extra fields for schema safety."""

    model_config = ConfigDict(frozen=True, extra="forbid")


class LoudnessMetrics(_Frozen):
    """BS.1770-5 integrated loudness + per-channel and ungated variants.

    Field semantics (ADR-0004):
        - ``lufs_i_stereo``: spec-compliant integrated loudness (stereo-combined).
        - ``single_channel_lufs_l/r``: per-channel K-weighted gated mean.
        - ``single_channel_lufs_ungated_l/r``: gate-free fallback for diagnostic.
        - ``delta_lu``: ``single_channel_lufs_l − single_channel_lufs_r`` with
          NaN propagation when either side is ``-inf``.
        - ``delta_lu_ungated``: same delta on the ungated values.
    """

    lufs_i_stereo: float
    single_channel_lufs_l: float
    single_channel_lufs_r: float
    single_channel_lufs_ungated_l: float
    single_channel_lufs_ungated_r: float
    delta_lu: float
    delta_lu_ungated: float


class LRAMetrics(_Frozen):
    """EBU R128 loudness range + max short-term loudness.

    Field semantics:
        - ``lra_lu``: ``P95 − P10`` of gated short-term loudness in LU.
        - ``max_short_term_lufs``: maximum short-term loudness over the file,
          used by :func:`asmr_balance.metrics.dynamics.derive_psr_db`.
    """

    lra_lu: float
    max_short_term_lufs: float


class StereoCorrelationMetrics(_Frozen):
    """Pearson L/R correlation and mid-side energy ratio.

    Field semantics:
        - ``pearson_r``: ``[-1, 1]``; ``≥ 0.95`` triggers the pseudo-mono rule.
        - ``ms_ratio_db``: ``10·log10(Σ M² / Σ S²)``; large positive values
          mean the side channel is anaemic (mono-narrow).
    """

    pearson_r: float
    ms_ratio_db: float


class BandImbalanceMetrics(_Frozen):
    """Per-band L/R imbalance in dB.

    Always-on 31-band 1/3-octave plus the legacy 4-band roll-up. The 4-band
    fields are exact partition sums of the 31-band energies (no extra IIR).

    All values are ``10·log10(Σ L² / Σ R²)`` in dB. Positive ⇒ L-louder,
    negative ⇒ R-louder. ``NaN`` propagates when either side has zero energy.
    """

    low: float
    low_mid: float
    high_mid: float
    high: float
    third_octave: dict[str, float]


class SlidingMetrics(_Frozen):
    """Per-block ΔLU summary over the BS.1770 z-block stream.

    Field semantics:
        - ``max_lu``: max ``|L − R|`` over per-block loudness pairs (LU).
        - ``p95_lu``: 95th percentile of ``|L − R|`` (sustained imbalance).
        - ``std_lu``: standard deviation of signed ``L − R``.
        - ``t_max_sec``: time of the ``max_lu`` block (seconds from file start).
    """

    max_lu: float
    p95_lu: float
    std_lu: float
    t_max_sec: float


class PhaseMetrics(_Frozen):
    """Low-band (<300 Hz) L/R phase coherence (Pearson on LPF signals)."""

    low_phase_coherence: float


class DynamicsMetrics(_Frozen):
    """True-peak dBTP and the peak-to-short-term loudness ratio.

    Field semantics:
        - ``true_peak_dbtp_l/r``: max ``|x_oversampled|`` in dBTP (BS.1770-5 Annex 2).
        - ``true_peak_dbtp_max``: ``max(l, r)`` for convenience.
        - ``psr_db``: ``true_peak_dbtp_max − max_short_term_lufs``; high values
          (> 20 dB) indicate quiet content with occasional peaks (typical ASMR).
    """

    true_peak_dbtp_l: float
    true_peak_dbtp_r: float
    true_peak_dbtp_max: float
    psr_db: float
