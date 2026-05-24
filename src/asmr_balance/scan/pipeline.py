"""Single-file scan pipeline.

The function is intentionally short: it materializes the source ADT, dispatches
on it, runs the graph for non-skipped files, assembles the record, evaluates
the rule set, and returns a :class:`FileResult`. All branching is explicit
and exhaustively handled.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, assert_never

from asmr_balance.algebra.semilattice import Verdict
from asmr_balance.graph.frozen import FrozenGraph
from asmr_balance.graph.scheduler import run
from asmr_balance.metrics.record import FileMeta, MetricRecord, ScanStatus
from asmr_balance.rules.algebra import Flag, evaluate
from asmr_balance.rules.builtin import DEFAULT_RULES
from asmr_balance.scan.assemble import assemble_record, build_default_graph
from asmr_balance.source.adt import LayoutPolicy, SkipLayout, SkipMono, Source
from asmr_balance.source.backend.dispatch import probe
from asmr_balance.source.open import open_source

if TYPE_CHECKING:
    from pathlib import Path

    from asmr_balance.config.model import Config


ProgressCallback = Callable[[str, int, int], None]
"""``(stage, current, total)`` reported at every pipeline stage boundary.

Stage tokens (lower-case, stable wire identifiers):

* ``probe``     — file header + duration probe (``0/1`` → ``1/1``)
* ``decode``    — decoder/backend selection (``0/1`` → ``1/1``)
* ``analyze``   — block-by-block streaming graph drive
  (``i/total_blocks`` ticked once per block)
* ``assemble``  — reducer outputs → MetricRecord
* ``evaluate``  — rule predicates → flags + verdict
* ``complete``  — pipeline finished (``1/1``); always emitted last
* ``skipped``   — file is mono / unsupported layout, no analysis to do
"""


@dataclass(frozen=True, slots=True)
class FileResult:
    """Outcome of one ``scan_one`` call — record + flags + verdict + elapsed."""

    record: MetricRecord
    flags: tuple[Flag, ...]
    verdict: Verdict
    elapsed_sec: float


def scan_one(
    path: Path,
    config: Config,
    *,
    on_progress: ProgressCallback | None = None,
) -> FileResult:
    """Analyze one file end-to-end, returning a :class:`FileResult`.

    Decode failures propagate as exceptions; layout-policy skips return a
    :class:`MetricRecord` with status :class:`ScanStatus.SKIPPED`.

    When ``on_progress`` is supplied it is invoked at every stage boundary
    (and once per block during ``analyze``) — see :data:`ProgressCallback`
    for the contract. The callback runs in the same thread as ``scan_one``;
    cross-thread bridging (e.g. ``loop.call_soon_threadsafe``) is the
    caller's responsibility.
    """
    t0 = time.perf_counter()
    try:
        result = _scan_inner(path, config, on_progress)
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
    if on_progress is not None:
        on_progress("complete", 1, 1)
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


def _scan_inner(
    path: Path,
    config: Config,
    on_progress: ProgressCallback | None,
) -> _InnerResult:
    progress = _ProgressSink(on_progress)
    progress.tick("probe", 0, 1)
    probed = probe(path)
    block_samples = max(1, round(probed.sample_rate * config.block_duration_sec))
    total_blocks = max(1, probed.n_frames // block_samples) if probed.n_frames > 0 else 0
    progress.tick("probe", 1, 1)

    progress.tick("decode", 0, 1)
    source_result = open_source(path, config.layout_policy, block_samples)
    progress.tick("decode", 1, 1)

    match source_result:
        case SkipMono() | SkipLayout() as skip:
            progress.tick("skipped", 1, 1)
            record = MetricRecord(
                meta=skip.meta,
                status=ScanStatus.SKIPPED,
                skip_reason=skip.reason,
            )
            return _InnerResult(record=record, flags=(), verdict=Verdict.OK)
        case Source() as src:
            return _analyze_source(src, config, total_blocks=total_blocks, progress=progress)
        case _:  # pragma: no cover  -- exhaustive match safety net
            assert_never(source_result)


def _analyze_source(
    src: Source,
    config: Config,
    *,
    total_blocks: int,
    progress: _ProgressSink,
) -> _InnerResult:
    """Run the graph + assemble + evaluate on a non-skipped source."""
    graph = _build_graph_for(src, config)
    progress.tick("analyze", 0, total_blocks)
    scheduler_output = run(
        graph,
        src,
        on_block=progress.analyze_block_callback(),
        total_blocks=total_blocks,
    )
    progress.tick("assemble", 0, 1)
    record = assemble_record(src.meta, scheduler_output)
    progress.tick("assemble", 1, 1)
    progress.tick("evaluate", 0, 1)
    judge_result = evaluate(DEFAULT_RULES, record, config.thresholds)
    progress.tick("evaluate", 1, 1)
    return _InnerResult(
        record=record,
        flags=judge_result.flags,
        verdict=judge_result.verdict,
    )


@dataclass(frozen=True, slots=True)
class _ProgressSink:
    """Thin wrapper that drops every call when no callback is wired.

    Keeps :func:`_scan_inner` readable by removing the ``if on_progress is not
    None`` litany at every boundary, and lets us hand the scheduler a typed
    ``on_block`` callback without a conditional lambda.
    """

    cb: ProgressCallback | None

    def tick(self, stage: str, current: int, total: int) -> None:
        if self.cb is not None:
            self.cb(stage, current, total)

    def analyze_block_callback(self) -> Callable[[int, int], None] | None:
        if self.cb is None:
            return None
        cb = self.cb
        return lambda done, total: cb("analyze", done, total)


def _build_graph_for(src: Source, config: Config) -> FrozenGraph:
    # NATIVE_WEIGHTED would skip balance reducers — not exposed in the default
    # graph yet (Phase E). For DOWNMIX / FL_FR we use the canonical graph.
    _ = LayoutPolicy.NATIVE_WEIGHTED  # placeholder to keep the enum import warm
    return build_default_graph(config, sample_rate=src.meta.sample_rate)
