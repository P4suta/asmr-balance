"""Wire-format DTOs for the Web API.

The DTOs are the **only** types that cross the HTTP boundary. They are
constructed from domain values (``FileResult``, ``MetricRecord``, ``Flag``,
``Verdict``) via ``from_*`` classmethods, so the routing layer never assembles
ad-hoc dicts and the OpenAPI schema is automatically accurate.
"""

from __future__ import annotations

from typing import Any, Self

from pydantic import BaseModel, ConfigDict, Field

from asmr_balance.metrics.record import MetricRecord
from asmr_balance.rules.algebra import Flag
from asmr_balance.scan.pipeline import FileResult


class HealthResponse(BaseModel):
    """Liveness probe payload."""

    model_config = ConfigDict(frozen=True)

    status: str
    version: str


class SchemaResponse(BaseModel):
    """Canonical column-name list shared by every sink."""

    model_config = ConfigDict(frozen=True)

    columns: tuple[str, ...]


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
    422: {"model": ErrorEnvelope, "description": "Validation or decode error"},
    500: {"model": ErrorEnvelope, "description": "Internal server error"},
}
"""OpenAPI ``responses`` fragment every route includes by default."""

INSPECT_ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    **COMMON_ERROR_RESPONSES,
    415: {"model": ErrorEnvelope, "description": "Unsupported audio format"},
}
"""Inspect endpoints additionally document the 415 path."""
