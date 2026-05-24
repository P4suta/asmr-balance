from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest

from asmr_balance.web.runtime.jobs import Job, JobRegistry, JobState
from asmr_balance.web.use_cases.errors import JobNotFoundError


def _make_job(out_dir: Path) -> Job:
    return Job(
        id=uuid4(),
        requested_paths=("album",),
        resolved_files=(out_dir / "a.wav", out_dir / "b.wav"),
        out_dir=out_dir,
        queue=asyncio.Queue(),
        started_at=datetime.now(UTC),
    )


def test_register_and_get(tmp_path: Path) -> None:
    registry = JobRegistry()
    job = _make_job(tmp_path)
    registry.register(job)
    assert registry.get(job.id) is job
    assert job.id in registry


def test_get_missing_raises_not_found() -> None:
    registry = JobRegistry()
    missing = uuid4()
    with pytest.raises(JobNotFoundError) as exc_info:
        registry.get(missing)
    assert exc_info.value.job_id == str(missing)
    assert exc_info.value.status_code == 404
    assert missing not in registry


def test_total_files_reflects_resolved(tmp_path: Path) -> None:
    job = _make_job(tmp_path)
    assert job.total_files == 2


def test_default_state_is_running(tmp_path: Path) -> None:
    job = _make_job(tmp_path)
    assert job.state is JobState.RUNNING
    assert job.completed_at is None
    assert job.failed_reason is None
