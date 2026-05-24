"""Scan job lifecycle endpoints.

``POST /api/scan`` starts a job. ``GET /api/scan/{id}`` snapshots its state.
``GET /api/scan/{id}/events`` is the SSE stream — one event per file plus a
terminal ``done`` event. ``GET /api/scan/{id}/report.{parquet,html,json}``
serves the per-job report files written by the existing sinks into
``out_dir``.
"""

from __future__ import annotations

from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from fastapi.responses import FileResponse
from sse_starlette.sse import EventSourceResponse

from asmr_balance.web.dto import (
    COMMON_ERROR_RESPONSES,
    ScanJobRequest,
    ScanJobResponse,
    ScanJobStatus,
)
from asmr_balance.web.runtime.jobs import JobRegistry, JobState
from asmr_balance.web.use_cases.errors import ScanReportNotReadyError
from asmr_balance.web.use_cases.scan import start_scan_job

router = APIRouter(prefix="/api", tags=["scan"])


def get_registry(request: Request) -> JobRegistry:
    """FastAPI dependency — pull the per-app singleton from ``app.state``."""
    return request.app.state.job_registry


@router.post(
    "/scan",
    response_model=ScanJobResponse,
    responses=COMMON_ERROR_RESPONSES,
)
async def start_scan(
    body: ScanJobRequest,
    registry: Annotated[JobRegistry, Depends(get_registry)],
) -> ScanJobResponse:
    """Start a new scan job; returns the handle immediately."""
    job = await start_scan_job(registry, body.paths)
    return ScanJobResponse.from_job(job)


@router.get(
    "/scan/{job_id}",
    response_model=ScanJobStatus,
    responses=COMMON_ERROR_RESPONSES,
)
def get_scan_status(
    job_id: UUID,
    registry: Annotated[JobRegistry, Depends(get_registry)],
) -> ScanJobStatus:
    """Return the current snapshot of the job lifecycle."""
    job = registry.get(job_id)
    return ScanJobStatus.from_job(job)


@router.get("/scan/{job_id}/events", responses=COMMON_ERROR_RESPONSES)
async def scan_events(
    job_id: UUID,
    registry: Annotated[JobRegistry, Depends(get_registry)],
) -> EventSourceResponse:
    """SSE stream: one ``file_done`` per scanned file, then a ``done`` sentinel."""
    job = registry.get(job_id)

    async def event_generator() -> object:
        while True:
            item = await job.queue.get()
            if item is None:
                yield {"event": "done", "data": "{}"}
                return
            yield {"event": "file_done", "data": item.model_dump_json()}

    return EventSourceResponse(event_generator())


_REPORT_NAMES: dict[str, tuple[str, str]] = {
    "parquet": ("report.parquet", "application/vnd.apache.parquet"),
    "html": ("report.html", "text/html"),
}


@router.get("/scan/{job_id}/report.{ext}", responses=COMMON_ERROR_RESPONSES)
def get_scan_report(
    job_id: UUID,
    ext: Literal["parquet", "html"],
    registry: Annotated[JobRegistry, Depends(get_registry)],
) -> FileResponse:
    """Serve the per-job report file written into ``out_dir``."""
    job = registry.get(job_id)
    if job.state is not JobState.DONE:
        raise ScanReportNotReadyError(
            str(job.id), state=job.state.value, reason="scan still running"
        )
    filename, media_type = _REPORT_NAMES[ext]
    target = job.out_dir / filename
    if not target.exists():
        raise ScanReportNotReadyError(
            str(job.id), state=job.state.value, reason=f"report.{ext} missing"
        )
    return FileResponse(target, media_type=media_type, filename=filename)
