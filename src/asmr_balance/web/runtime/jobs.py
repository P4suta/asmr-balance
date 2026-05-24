"""In-process job registry — one :class:`Job` per scan request.

The registry is an in-memory ``dict[UUID, Job]``. State is intentionally
lost on process restart; this matches the localhost / single-user
assumption (ADR-0014). Persistent history is deferred to Phase 3.

:class:`Job` is a frozen-shape dataclass (mutable counters, immutable
identity). State transitions are owned by the orchestrator in
:mod:`asmr_balance.web.use_cases.scan` — the registry just stores and
retrieves.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Any
from uuid import UUID

from asmr_balance.web.use_cases.errors import JobNotFoundError


class JobState(StrEnum):
    """Lifecycle of one scan job."""

    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


@dataclass(slots=True)
class Job:
    """One scan job — requested rel-paths + resolved audio files + lifecycle.

    ``done_event`` fires when the orchestrator transitions ``state`` to a
    terminal value (DONE / FAILED). Any consumer (tests, future schedulers,
    in-process job-followers) can ``await job.done_event.wait()`` instead of
    polling ``state``.
    """

    id: UUID
    requested_paths: tuple[str, ...]
    resolved_files: tuple[Path, ...]
    out_dir: Path
    queue: asyncio.Queue[Any]
    started_at: datetime
    state: JobState = JobState.RUNNING
    completed_at: datetime | None = None
    failed_reason: str | None = None
    done_event: asyncio.Event = field(default_factory=asyncio.Event)

    @property
    def total_files(self) -> int:
        return len(self.resolved_files)


@dataclass(slots=True)
class JobRegistry:
    """Map ``UUID → Job``. Tiny, in-process, no locking (single event loop)."""

    _jobs: dict[UUID, Job] = field(default_factory=dict)

    def register(self, job: Job) -> None:
        self._jobs[job.id] = job

    def get(self, job_id: UUID) -> Job:
        try:
            return self._jobs[job_id]
        except KeyError as exc:
            raise JobNotFoundError(str(job_id)) from exc

    def __contains__(self, job_id: UUID) -> bool:
        return job_id in self._jobs
