"""Scan job lifecycle endpoints.

``POST /api/scan`` starts a job. ``GET /api/scan/{id}`` snapshots its state.
``GET /api/scan/{id}/stream`` is the NDJSON stream — one ``file_done`` frame
per scanned file, terminated by either ``done`` (success) or ``failed``
(mid-flight crash). ``GET /api/scan/{id}/report.{parquet,html}`` serves the
per-job report files written by the existing sinks into ``out_dir``.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from fastapi.responses import FileResponse, StreamingResponse

from asmr_balance.web.dto import (
    COMMON_ERROR_RESPONSES,
    ScanDoneEvent,
    ScanFailedEvent,
    ScanJobRequest,
    ScanJobResponse,
    ScanJobStatus,
)
from asmr_balance.web.runtime.jobs import JobRegistry, JobState
from asmr_balance.web.use_cases.errors import ScanReportNotReadyError
from asmr_balance.web.use_cases.scan import start_scan_job

NDJSON_MEDIA_TYPE = "application/x-ndjson"

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


@router.get("/scan/{job_id}/stream", responses=COMMON_ERROR_RESPONSES)
async def scan_stream(
    job_id: UUID,
    registry: Annotated[JobRegistry, Depends(get_registry)],
) -> StreamingResponse:
    """NDJSON stream — one ``file_done`` per scanned file plus a terminal frame.

    Frames carry a ``type`` discriminator. ``file_done`` is :class:`ScanFileEvent`;
    the terminal frame is :class:`ScanDoneEvent` on success or
    :class:`ScanFailedEvent` (carrying ``Job.failed_reason``) if the background
    task crashed mid-flight. Status of the JobRegistry lookup itself is still
    HTTP-shaped — a missing job 404s before the stream opens.
    """
    job = registry.get(job_id)

    async def frames() -> AsyncIterator[bytes]:
        while True:
            item = await job.queue.get()
            if item is None:
                if job.state is JobState.FAILED:
                    failed = ScanFailedEvent(detail=job.failed_reason or "scan failed")
                    yield (failed.model_dump_json() + "\n").encode("utf-8")
                else:
                    yield (ScanDoneEvent().model_dump_json() + "\n").encode("utf-8")
                return
            yield (item.model_dump_json() + "\n").encode("utf-8")

    return StreamingResponse(frames(), media_type=NDJSON_MEDIA_TYPE)


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
