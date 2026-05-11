"""Per-file pipeline: decode → stream → analyzers → MetricRecord → flags.

Phase B implements the **sequential** form.  Phase D will lift this into
``concurrent.futures.ProcessPoolExecutor`` for file-level parallelism (ADR-0001).
"""

from __future__ import annotations

import math
import time
from typing import TYPE_CHECKING, Final

from asmr_balance.analyzers import Analyzer, build_analyzers
from asmr_balance.decode import AudioMetadata, probe
from asmr_balance.flags import judge
from asmr_balance.logging import get_logger
from asmr_balance.stream import iter_stereo_blocks, should_skip, skip_reason
from asmr_balance.types import FileResult, MetricRecord, Verdict

if TYPE_CHECKING:
    from collections.abc import Iterable
    from pathlib import Path

    from asmr_balance.config import Config

_log = get_logger(__name__)

_AUDIO_EXTENSIONS: Final[frozenset[str]] = frozenset(
    {
        ".wav",
        ".flac",
        ".ogg",
        ".opus",
        ".aiff",
        ".aif",
        ".au",
        ".m4a",
        ".mp3",
        ".mp4",
        ".mkv",
        ".webm",
        ".mov",
    }
)


def find_audio_files(root: Path) -> list[Path]:
    """Return audio/video files under ``root`` (recursively), sorted by path."""
    if root.is_file():
        return [root]
    return sorted(
        p for p in root.rglob("*") if p.is_file() and p.suffix.lower() in _AUDIO_EXTENSIONS
    )


def scan_one(path: Path, config: Config) -> FileResult:
    """Analyse one file end-to-end."""
    t0 = time.perf_counter()
    metadata = probe(path)
    if should_skip(metadata.n_channels, config.layout_policy):
        metrics = _skipped_record(metadata, skip_reason(metadata.n_channels, config.layout_policy))
        elapsed = time.perf_counter() - t0
        _log.info(
            "skipped",
            file=str(path),
            layout=metadata.layout_name,
            reason=metrics.skip_reason,
            elapsed_sec=elapsed,
        )
        return FileResult(metrics=metrics, flags=(), verdict=Verdict.OK)

    block_samples = max(1, config.block_samples)
    analyzers = build_analyzers(config, sample_rate=metadata.sample_rate)
    _consume(analyzers, iter_stereo_blocks(metadata, config.layout_policy, block_samples))

    record = _build_record(metadata, analyzers)
    flags, verdict = judge(record, config.flag_thresholds)
    elapsed = time.perf_counter() - t0
    _log.info(
        "scanned",
        file=str(path),
        verdict=verdict.value,
        flag_count=len(flags),
        elapsed_sec=elapsed,
    )
    return FileResult(metrics=record, flags=tuple(flags), verdict=verdict)


def scan_many(paths: Iterable[Path], config: Config) -> list[FileResult]:
    """Sequential scan over an iterable of file paths (Phase B)."""
    results: list[FileResult] = []
    for p in paths:
        try:
            results.append(scan_one(p, config))
        except Exception as exc:  # noqa: BLE001
            _log.exception("scan_error", file=str(p), error_type=type(exc).__name__)
            results.append(_error_result(p, exc))
    return results


# --- internals --------------------------------------------------------------


def _consume(analyzers: list[Analyzer], blocks: Iterable) -> None:
    for block in blocks:
        for an in analyzers:
            an.push(block)


def _build_record(metadata: AudioMetadata, analyzers: list[Analyzer]) -> MetricRecord:
    merged: dict[str, float] = {}
    for an in analyzers:
        merged.update(an.finalize())
    return MetricRecord(
        file_path=metadata.path,
        sample_rate=metadata.sample_rate,
        duration_sec=metadata.duration_sec,
        channel_layout=metadata.layout_name,
        skipped=False,
        skip_reason=None,
        lufs_i_stereo=merged.get("lufs_i_stereo", float("nan")),
        single_channel_lufs_l=merged.get("single_channel_lufs_l", float("nan")),
        single_channel_lufs_r=merged.get("single_channel_lufs_r", float("nan")),
        single_channel_lufs_ungated_l=merged.get("single_channel_lufs_ungated_l", float("nan")),
        single_channel_lufs_ungated_r=merged.get("single_channel_lufs_ungated_r", float("nan")),
        delta_lu=merged.get("delta_lu", float("nan")),
        delta_lu_ungated=merged.get("delta_lu_ungated", float("nan")),
        pearson_r=merged.get("pearson_r", float("nan")),
        ms_ratio_db=merged.get("ms_ratio_db", float("nan")),
        band_imbalance_low=merged.get("band_imbalance_low", float("nan")),
        band_imbalance_low_mid=merged.get("band_imbalance_low_mid", float("nan")),
        band_imbalance_high_mid=merged.get("band_imbalance_high_mid", float("nan")),
        band_imbalance_high=merged.get("band_imbalance_high", float("nan")),
        sliding_max_lu=merged.get("sliding_max_lu", float("nan")),
        sliding_p95_lu=merged.get("sliding_p95_lu", float("nan")),
        sliding_std_lu=merged.get("sliding_std_lu", float("nan")),
        sliding_t_max_sec=merged.get("sliding_t_max_sec", float("nan")),
        low_phase_coherence=merged.get("low_phase_coherence", float("nan")),
    )


def _skipped_record(metadata: AudioMetadata, reason: str) -> MetricRecord:
    return MetricRecord(
        file_path=metadata.path,
        sample_rate=metadata.sample_rate,
        duration_sec=metadata.duration_sec,
        channel_layout=metadata.layout_name,
        skipped=True,
        skip_reason=reason,
    )


def _error_result(path: Path, exc: BaseException) -> FileResult:
    metrics = MetricRecord(
        file_path=path,
        sample_rate=0,
        duration_sec=math.nan,
        channel_layout="unknown",
        skipped=True,
        skip_reason=f"{type(exc).__name__}: {exc}",
    )
    return FileResult(metrics=metrics, flags=(), verdict=Verdict.FAIL)
