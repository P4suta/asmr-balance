"""Sink protocol + result flattening to dotted dict.

The flattening is the single place where the nested
:class:`~asmr_balance.metrics.record.MetricRecord` is projected to a flat
column-name space. All three concrete sinks share the dotted name space
(:data:`COLUMN_NAMES`); diverging name policy would create silent schema
drift between formats.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol

from asmr_balance.metrics.record import MetricRecord
from asmr_balance.nodes.bandsplit import BANDS

if TYPE_CHECKING:
    from collections.abc import Iterable

    from asmr_balance.scan.pipeline import FileResult


class Sink(Protocol):
    """Open → write* → close.

    Implementations are *not* expected to be re-entrant. The pipeline opens
    each sink once at the start of a scan, calls :meth:`write` per file,
    and closes each at the end (even on error — via ``try / finally``).
    """

    def open(self) -> None: ...
    def write(self, result: FileResult) -> None: ...
    def close(self) -> None: ...


# ---------------------------------------------------------------------------
# Canonical flat column names
# ---------------------------------------------------------------------------
def _band_third_oct_col(band_name: str) -> str:
    return f"band.third_octave.{band_name}"


COLUMN_NAMES: tuple[str, ...] = (
    # File metadata
    "meta.file_path",
    "meta.sample_rate",
    "meta.duration_sec",
    "meta.channel_layout",
    # Status
    "status",
    "skip_reason",
    # Loudness
    "loudness.lufs_i_stereo",
    "loudness.single_channel_lufs_l",
    "loudness.single_channel_lufs_r",
    "loudness.single_channel_lufs_ungated_l",
    "loudness.single_channel_lufs_ungated_r",
    "loudness.delta_lu",
    "loudness.delta_lu_ungated",
    # LRA
    "lra.lra_lu",
    "lra.max_short_term_lufs",
    # Correlation
    "correlation.pearson_r",
    "correlation.ms_ratio_db",
    # Band 4-band aggregates
    "band.low",
    "band.low_mid",
    "band.high_mid",
    "band.high",
    # Band 31 third-octave entries
    *(_band_third_oct_col(b.name) for b in BANDS),
    # Sliding
    "sliding.max_lu",
    "sliding.p95_lu",
    "sliding.std_lu",
    "sliding.t_max_sec",
    # Phase
    "phase.low_phase_coherence",
    # Dynamics
    "dynamics.true_peak_dbtp_l",
    "dynamics.true_peak_dbtp_r",
    "dynamics.true_peak_dbtp_max",
    "dynamics.psr_db",
    # Flags + verdict
    "flag_codes",
    "verdict",
)
"""All dotted column names emitted by the sinks. Order is the canonical
schema order — parquet column ordering, HTML table column ordering, and TUI
inspector field listing all follow this."""


def result_to_flat_row(result: FileResult) -> dict[str, Any]:
    """Project a :class:`FileResult` to a dict keyed by :data:`COLUMN_NAMES`."""
    record: MetricRecord = result.record
    row: dict[str, Any] = dict.fromkeys(COLUMN_NAMES)
    row["meta.file_path"] = str(record.meta.file_path)
    row["meta.sample_rate"] = record.meta.sample_rate
    row["meta.duration_sec"] = record.meta.duration_sec
    row["meta.channel_layout"] = record.meta.channel_layout
    row["status"] = record.status.value
    row["skip_reason"] = record.skip_reason

    if (lo := record.loudness) is not None:
        row["loudness.lufs_i_stereo"] = lo.lufs_i_stereo
        row["loudness.single_channel_lufs_l"] = lo.single_channel_lufs_l
        row["loudness.single_channel_lufs_r"] = lo.single_channel_lufs_r
        row["loudness.single_channel_lufs_ungated_l"] = lo.single_channel_lufs_ungated_l
        row["loudness.single_channel_lufs_ungated_r"] = lo.single_channel_lufs_ungated_r
        row["loudness.delta_lu"] = lo.delta_lu
        row["loudness.delta_lu_ungated"] = lo.delta_lu_ungated

    if (lra := record.lra) is not None:
        row["lra.lra_lu"] = lra.lra_lu
        row["lra.max_short_term_lufs"] = lra.max_short_term_lufs

    if (corr := record.correlation) is not None:
        row["correlation.pearson_r"] = corr.pearson_r
        row["correlation.ms_ratio_db"] = corr.ms_ratio_db

    if (band := record.band) is not None:
        row["band.low"] = band.low
        row["band.low_mid"] = band.low_mid
        row["band.high_mid"] = band.high_mid
        row["band.high"] = band.high
        for b in BANDS:
            row[_band_third_oct_col(b.name)] = band.third_octave.get(b.name)

    if (sliding := record.sliding) is not None:
        row["sliding.max_lu"] = sliding.max_lu
        row["sliding.p95_lu"] = sliding.p95_lu
        row["sliding.std_lu"] = sliding.std_lu
        row["sliding.t_max_sec"] = sliding.t_max_sec

    if (phase := record.phase) is not None:
        row["phase.low_phase_coherence"] = phase.low_phase_coherence

    if (dyn := record.dynamics) is not None:
        row["dynamics.true_peak_dbtp_l"] = dyn.true_peak_dbtp_l
        row["dynamics.true_peak_dbtp_r"] = dyn.true_peak_dbtp_r
        row["dynamics.true_peak_dbtp_max"] = dyn.true_peak_dbtp_max
        row["dynamics.psr_db"] = dyn.psr_db

    row["flag_codes"] = [f.code for f in result.flags]
    row["verdict"] = result.verdict.name
    return row


def build_sinks(
    out_parquet: Iterable[str] | None,
    out_html: str | None,
    show_summary: bool,
) -> list[Sink]:
    """Compose the sink list from CLI flags. Parquet is always present."""
    from asmr_balance.sink.html import HtmlSink
    from asmr_balance.sink.parquet import ParquetSink
    from asmr_balance.sink.tui import TuiSummarySink

    sinks: list[Sink] = []
    if out_parquet is not None:
        sinks.extend(ParquetSink(path=path) for path in out_parquet)
    if out_html is not None:
        sinks.append(HtmlSink(path=out_html))
    if show_summary:
        sinks.append(TuiSummarySink())
    return sinks
