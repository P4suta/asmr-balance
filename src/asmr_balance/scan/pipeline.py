"""Single-file scan pipeline.

The function is intentionally short: it materializes the source ADT, dispatches
on it, runs the graph for non-skipped files, assembles the record, evaluates
the rule set, and returns a :class:`FileResult`. All branching is explicit
and exhaustively handled.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, assert_never

from asmr_balance.algebra.semilattice import Verdict
from asmr_balance.graph.scheduler import run
from asmr_balance.metrics.record import FileMeta, MetricRecord, ScanStatus
from asmr_balance.rules.algebra import Flag, evaluate
from asmr_balance.rules.builtin import DEFAULT_RULES
from asmr_balance.scan.assemble import assemble_record, build_default_graph
from asmr_balance.source.adt import LayoutPolicy, SkipLayout, SkipMono, Source
from asmr_balance.source.open import open_source

if TYPE_CHECKING:
    from pathlib import Path

    from asmr_balance.config.model import Config


@dataclass(frozen=True, slots=True)
class FileResult:
    """Outcome of one ``scan_one`` call — record + flags + verdict + elapsed."""

    record: MetricRecord
    flags: tuple[Flag, ...]
    verdict: Verdict
    elapsed_sec: float


def scan_one(path: Path, config: Config) -> FileResult:
    """Analyze one file end-to-end, returning a :class:`FileResult`.

    Decode failures propagate as exceptions; layout-policy skips return a
    :class:`MetricRecord` with status :class:`ScanStatus.SKIPPED`.
    """
    t0 = time.perf_counter()
    try:
        result = _scan_inner(path, config)
    except Exception as exc:  # noqa: BLE001
        elapsed = time.perf_counter() - t0
        meta = FileMeta(file_path=path, sample_rate=0, duration_sec=0.0, channel_layout="unknown")
        record = MetricRecord(
            meta=meta,
            status=ScanStatus.ERRORED,
            skip_reason=f"{type(exc).__name__}: {exc}",
        )
        return FileResult(record=record, flags=(), verdict=Verdict.OK, elapsed_sec=elapsed)
    elapsed = time.perf_counter() - t0
    return FileResult(
        record=result.record,
        flags=result.flags,
        verdict=result.verdict,
        elapsed_sec=elapsed,
    )


@dataclass(frozen=True, slots=True)
class _InnerResult:
    record: MetricRecord
    flags: tuple[Flag, ...]
    verdict: Verdict


def _scan_inner(path: Path, config: Config) -> _InnerResult:
    source_result = open_source(path, config.layout_policy, _block_samples_for(config, path))
    match source_result:
        case SkipMono() | SkipLayout() as skip:
            record = MetricRecord(
                meta=skip.meta,
                status=ScanStatus.SKIPPED,
                skip_reason=skip.reason,
            )
            return _InnerResult(record=record, flags=(), verdict=Verdict.OK)
        case Source() as src:
            graph = _build_graph_for(src, config)
            scheduler_output = run(graph, src)
            record = assemble_record(src.meta, scheduler_output)
            judge_result = evaluate(DEFAULT_RULES, record, config.thresholds)
            return _InnerResult(
                record=record,
                flags=judge_result.flags,
                verdict=judge_result.verdict,
            )
        case _:
            assert_never(source_result)


def _build_graph_for(src: Source, config: Config):
    # NATIVE_WEIGHTED would skip balance reducers — not exposed in the default
    # graph yet (Phase E). For DOWNMIX / FL_FR we use the canonical graph.
    _ = LayoutPolicy.NATIVE_WEIGHTED  # placeholder to keep the enum import warm
    return build_default_graph(config, sample_rate=src.meta.sample_rate)


def _block_samples_for(config: Config, path: Path) -> int:
    """Pre-probe the file to derive a sample-rate-relative block size.

    ASMR masters routinely ship at 96 / 192 kHz; a fixed 4800-sample block
    would be only 25 ms there, multiplying the per-block Python overhead by
    4x. We probe once cheaply and pick ``round(sample_rate * block_duration_sec)``.
    """
    from asmr_balance.source.backend.dispatch import probe

    probed = probe(path)
    return max(1, round(probed.sample_rate * config.block_duration_sec))
