from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from asmr_balance.web.runtime.jobs import JobRegistry, JobState
from asmr_balance.web.use_cases import scan as scan_module
from asmr_balance.web.use_cases.errors import (
    EmptyScanRequestError,
    LibraryPathError,
)
from asmr_balance.web.use_cases.scan import start_scan_job
from tests.fixtures.gen_fixtures import write_balanced_tone

_WAIT_TIMEOUT_SEC = 10.0


async def _wait_for_terminal(job) -> None:
    async with asyncio.timeout(_WAIT_TIMEOUT_SEC):
        await job.done_event.wait()


def test_start_scan_job_happy_path(library_root: Path, reports_root: Path) -> None:
    write_balanced_tone(library_root / "x.wav", duration_sec=0.5)

    async def runner() -> None:
        registry = JobRegistry()
        job = await start_scan_job(registry, ["x.wav"])
        assert job.total_files == 1
        assert registry.get(job.id) is job
        await _wait_for_terminal(job)
        assert job.state is JobState.DONE
        assert job.failed_reason is None
        assert job.completed_at is not None
        assert (job.out_dir / "report.parquet").exists()

    asyncio.run(runner())


def test_start_scan_job_rejects_empty_paths(library_root: Path, reports_root: Path) -> None:
    (library_root / "empty").mkdir()

    async def runner() -> None:
        registry = JobRegistry()
        with pytest.raises(EmptyScanRequestError) as exc_info:
            await start_scan_job(registry, ["empty"])
        assert exc_info.value.status_code == 400

    asyncio.run(runner())


def test_start_scan_job_propagates_library_path_error(
    library_root: Path, reports_root: Path
) -> None:
    async def runner() -> None:
        registry = JobRegistry()
        with pytest.raises(LibraryPathError):
            await start_scan_job(registry, ["nope"])

    asyncio.run(runner())


def test_run_job_marks_failed_on_scan_exception(
    monkeypatch: pytest.MonkeyPatch,
    library_root: Path,
    reports_root: Path,
) -> None:
    write_balanced_tone(library_root / "x.wav", duration_sec=0.5)

    def fake_scan_many(*_args, **_kwargs):
        msg = "simulated failure"
        raise RuntimeError(msg)

    monkeypatch.setattr(scan_module, "scan_many", fake_scan_many)

    async def runner() -> None:
        registry = JobRegistry()
        job = await start_scan_job(registry, ["x.wav"])
        await _wait_for_terminal(job)
        assert job.state is JobState.FAILED
        assert "simulated failure" in (job.failed_reason or "")

    asyncio.run(runner())
