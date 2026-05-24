"""Wire-format DTOs for the Web API.

The DTOs are the **only** types that cross the HTTP boundary. They are
constructed from domain / runtime values via ``from_*`` classmethods, so
the routing layer never assembles ad-hoc dicts and the OpenAPI schema is
automatically accurate.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field

from asmr_balance.metrics.record import MetricRecord
from asmr_balance.rules.algebra import Flag
from asmr_balance.scan.pipeline import FileResult

if TYPE_CHECKING:
    from asmr_balance.web.runtime.jobs import Job
    from asmr_balance.web.use_cases.library import LibraryEntry


# ---------------------------------------------------------------------------
# meta / schema / health
# ---------------------------------------------------------------------------
class HealthResponse(BaseModel):
    """Liveness probe payload."""

    model_config = ConfigDict(frozen=True)

    status: str
    version: str


class SchemaResponse(BaseModel):
    """Canonical column-name list shared by every sink."""

    model_config = ConfigDict(frozen=True)

    columns: tuple[str, ...]


# ---------------------------------------------------------------------------
# inspect (Phase 1a)
# ---------------------------------------------------------------------------
class FlagDto(BaseModel):
    """Single rule firing flattened for the wire (severity as name)."""

    model_config = ConfigDict(frozen=True)

    code: str
    severity: str
    message: str

    @classmethod
    def from_flag(cls, flag: Flag) -> Self:
        return cls(code=flag.code, severity=flag.severity.name, message=flag.message)


class InspectResponse(BaseModel):
    """Result of one single-file ``/api/inspect`` call.

    The wire format embeds the full :class:`MetricRecord`; clients that want a
    flat column-keyed view can join with :class:`SchemaResponse`.
    """

    model_config = ConfigDict(frozen=True)

    source_name: str
    verdict: str
    elapsed_sec: float
    flags: tuple[FlagDto, ...]
    record: MetricRecord

    @classmethod
    def from_file_result(cls, result: FileResult, *, source_name: str) -> Self:
        return cls(
            source_name=source_name,
            verdict=result.verdict.name,
            elapsed_sec=result.elapsed_sec,
            flags=tuple(FlagDto.from_flag(f) for f in result.flags),
            record=result.record,
        )


# ---------------------------------------------------------------------------
# library browse (Phase 1b)
# ---------------------------------------------------------------------------
class LibraryEntryDto(BaseModel):
    """One file / directory under the library mount."""

    model_config = ConfigDict(frozen=True)

    name: str
    type: Literal["dir", "file"]
    rel_path: str
    is_audio: bool
    size: int | None

    @classmethod
    def from_entry(cls, entry: LibraryEntry) -> Self:
        return cls(
            name=entry.name,
            type=entry.type,  # pyright: ignore[reportArgumentType] -- runtime str narrowed by domain
            rel_path=entry.rel_path,
            is_audio=entry.is_audio,
            size=entry.size,
        )


class LibraryListing(BaseModel):
    """Response for ``GET /api/library`` and ``GET /api/library/{path}``."""

    model_config = ConfigDict(frozen=True)

    rel_path: str
    parent_rel_path: str | None
    entries: tuple[LibraryEntryDto, ...]


# ---------------------------------------------------------------------------
# scan jobs (Phase 1b)
# ---------------------------------------------------------------------------
class ScanJobRequest(BaseModel):
    """Body of ``POST /api/scan``."""

    model_config = ConfigDict(frozen=True)

    paths: tuple[str, ...] = Field(min_length=1)


class ScanJobResponse(BaseModel):
    """Response of ``POST /api/scan`` — created handle."""

    model_config = ConfigDict(frozen=True)

    job_id: str
    total_files: int
    requested_paths: tuple[str, ...]

    @classmethod
    def from_job(cls, job: Job) -> Self:
        return cls(
            job_id=str(job.id),
            total_files=job.total_files,
            requested_paths=job.requested_paths,
        )


class ScanJobStatus(BaseModel):
    """Response of ``GET /api/scan/{id}`` — full job lifecycle snapshot."""

    model_config = ConfigDict(frozen=True)

    job_id: str
    state: str
    total_files: int
    requested_paths: tuple[str, ...]
    started_at: datetime
    completed_at: datetime | None
    failed_reason: str | None

    @classmethod
    def from_job(cls, job: Job) -> Self:
        return cls(
            job_id=str(job.id),
            state=job.state.value,
            total_files=job.total_files,
            requested_paths=job.requested_paths,
            started_at=job.started_at,
            completed_at=job.completed_at,
            failed_reason=job.failed_reason,
        )


class ScanFileEvent(BaseModel):
    """SSE payload — one per file as the scan progresses."""

    model_config = ConfigDict(frozen=True)

    type: Literal["file_done"] = "file_done"
    sequence: int
    total: int
    source_name: str
    verdict: str
    elapsed_sec: float
    flag_codes: tuple[str, ...]
    record_status: str

    @classmethod
    def from_file_result(cls, result: FileResult, *, sequence: int, total: int) -> Self:
        return cls(
            sequence=sequence,
            total=total,
            source_name=result.record.meta.file_path.name,
            verdict=result.verdict.name,
            elapsed_sec=result.elapsed_sec,
            flag_codes=tuple(f.code for f in result.flags),
            record_status=result.record.status.value,
        )


# ---------------------------------------------------------------------------
# error envelope (shared)
# ---------------------------------------------------------------------------
class ErrorEnvelope(BaseModel):
    """Uniform error response shape used by every exception handler.

    The envelope is rich on purpose: callers (humans triaging UI failures,
    machines retrying, log greppers) all benefit from the same structured
    fields. ``context`` is free-form per error class — see
    :mod:`asmr_balance.web.use_cases.errors` for what each class emits.
    """

    model_config = ConfigDict(frozen=True)

    error: str
    """Exception class name (e.g. ``UnsupportedAudioFormatError``)."""

    detail: str
    """Human-readable single-sentence summary."""

    status: int
    """HTTP status code mirrored into the body for client convenience."""

    context: dict[str, Any] = Field(default_factory=dict)
    """Per-error structured context (suffix, supported list, traversal target, …)."""

    trace_id: str
    """Request UUID — also returned in the ``X-Request-ID`` response header."""


COMMON_ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    400: {"model": ErrorEnvelope, "description": "Bad request"},
    404: {"model": ErrorEnvelope, "description": "Not found"},
    422: {"model": ErrorEnvelope, "description": "Validation or decode error"},
    500: {"model": ErrorEnvelope, "description": "Internal server error"},
}
"""OpenAPI ``responses`` fragment every route includes by default."""

INSPECT_ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    **COMMON_ERROR_RESPONSES,
    415: {"model": ErrorEnvelope, "description": "Unsupported audio format"},
}
"""Inspect endpoints additionally document the 415 path."""
