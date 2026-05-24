"""Scan job orchestration use case.

The use case is small but its sequencing is load-bearing:

1. Resolve every requested rel-path into an absolute audio-file list
   *up front* — knowing ``total_files`` immediately means the NDJSON stream
   can report ``(seq, total)`` from the first event.
2. Register a fresh :class:`Job` with its own ``asyncio.Queue`` and per-job
   ``out_dir`` under ``reports_root()``.
3. Spawn an ``asyncio.create_task`` that runs the blocking scan on a worker
   thread (the existing :func:`scan_many` is sync and uses a
   :class:`ProcessPoolExecutor`; we force ``workers=1`` so sink callbacks
   run in this process — see ADR-0014).
4. On completion (success or exception) push a terminal sentinel onto the
   queue so the streaming handler emits its terminal frame and closes.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from asmr_balance.config.model import Config
from asmr_balance.scan.parallel import scan_many
from asmr_balance.sink.base import Sink, build_sinks
from asmr_balance.web.runtime.jobs import Job, JobRegistry, JobState
from asmr_balance.web.runtime.paths import reports_root
from asmr_balance.web.runtime.sinks import JsonStreamingSink
from asmr_balance.web.use_cases.errors import EmptyScanRequestError
from asmr_balance.web.use_cases.library import walk_audio_files

# Strong references to background tasks so they survive the lifetime of the
# scan job — without this the GC may collect the Task mid-flight (RUF006).
_BACKGROUND_TASKS: set[asyncio.Task[None]] = set()


def _session_config() -> Config:
    """Web-mode config — sequential scan + default thresholds."""
    return Config().with_overrides(workers=1)


async def start_scan_job(
    registry: JobRegistry,
    paths: Sequence[str],
    config: Config | None = None,
) -> Job:
    """Resolve files, create a :class:`Job`, kick off background analysis."""
    resolved: list[Path] = []
    for rel in paths:
        resolved.extend(walk_audio_files(rel))
    if not resolved:
        raise EmptyScanRequestError(tuple(paths))

    job_id = uuid4()
    out_dir = reports_root() / str(job_id)
    out_dir.mkdir(parents=True, exist_ok=True)

    job = Job(
        id=job_id,
        requested_paths=tuple(paths),
        resolved_files=tuple(resolved),
        out_dir=out_dir,
        queue=asyncio.Queue(),
        started_at=datetime.now(UTC),
    )
    registry.register(job)

    cfg = (config or _session_config()).with_overrides(workers=1)
    loop = asyncio.get_running_loop()
    task = asyncio.create_task(_run_job(job, cfg, loop))
    _BACKGROUND_TASKS.add(task)
    task.add_done_callback(_BACKGROUND_TASKS.discard)
    return job


async def _run_job(job: Job, config: Config, loop: asyncio.AbstractEventLoop) -> None:
    """Background task: drive the scan, push the terminal sentinel on exit."""
    sinks = _build_sinks_for(job, loop)
    try:
        await asyncio.to_thread(_drive_sinks, job.resolved_files, config, sinks)
        job.state = JobState.DONE
    except Exception as exc:  # noqa: BLE001 -- record every failure mode
        job.state = JobState.FAILED
        job.failed_reason = f"{type(exc).__name__}: {exc}"
    finally:
        job.completed_at = datetime.now(UTC)
        loop.call_soon_threadsafe(job.queue.put_nowait, None)
        job.done_event.set()


def _build_sinks_for(job: Job, loop: asyncio.AbstractEventLoop) -> list[Sink]:
    sinks = build_sinks(
        out_parquet=[str(job.out_dir / "report.parquet")],
        out_html=str(job.out_dir / "report.html"),
        show_summary=False,
    )
    sinks.append(JsonStreamingSink(loop=loop, queue=job.queue, total=job.total_files))
    return sinks


def _drive_sinks(paths: Iterable[Path], config: Config, sinks: list[Sink]) -> None:
    """Open each sink, write per-file results, close each sink — sync helper."""
    for sink in sinks:
        sink.open()
    try:
        for result in scan_many(paths, config):
            for sink in sinks:
                sink.write(result)
    finally:
        for sink in sinks:
            sink.close()
