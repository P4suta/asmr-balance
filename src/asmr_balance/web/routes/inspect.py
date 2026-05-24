"""HTTP boundary for the inspect use case.

This module owns *only* the adaptation between HTTP and the
:func:`perform_inspect` use case: parse the upload, project the domain result
to the response shape each endpoint serves. Error translation is delegated to
the centralized handlers in :mod:`asmr_balance.web.errors`; this module never
catches use case exceptions itself.

Two response shapes share one use case:

- ``POST /api/inspect`` — JSON (Pydantic :class:`InspectResponse`).
- ``POST /api/inspect/partial`` — HTML (HTMX partial; template receives the
  same DTO plus a pre-flattened ``Mapping`` of dotted column names).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, File, Request, UploadFile
from fastapi.responses import HTMLResponse

from asmr_balance.scan.pipeline import FileResult
from asmr_balance.sink.base import result_to_flat_row
from asmr_balance.web.dto import INSPECT_ERROR_RESPONSES, InspectResponse
from asmr_balance.web.use_cases.inspect import perform_inspect

router = APIRouter(prefix="/api", tags=["inspect"])


async def _execute(file: UploadFile) -> tuple[FileResult, str]:
    """Read the upload and run the use case once."""
    audio_bytes = await file.read()
    result = perform_inspect(audio_bytes, file.filename)
    return result, file.filename or "(unnamed)"


@router.post(
    "/inspect",
    response_model=InspectResponse,
    responses=INSPECT_ERROR_RESPONSES,
)
async def inspect_json(file: Annotated[UploadFile, File()]) -> InspectResponse:
    """JSON API: ``POST /api/inspect`` multipart → :class:`InspectResponse`."""
    result, source_name = await _execute(file)
    return InspectResponse.from_file_result(result, source_name=source_name)


@router.post(
    "/inspect/partial",
    response_class=HTMLResponse,
    responses=INSPECT_ERROR_RESPONSES,
)
async def inspect_partial(
    request: Request,
    file: Annotated[UploadFile, File()],
) -> HTMLResponse:
    """HTMX partial: returns the rendered result card.

    The template receives both the wire DTO and a pre-materialized flat
    column view (presentation concern — kept out of the JSON wire format).
    """
    result, source_name = await _execute(file)
    templates = request.app.state.templates
    return templates.TemplateResponse(
        request,
        "_inspect_result.html",
        {
            "response": InspectResponse.from_file_result(result, source_name=source_name),
            "flat": result_to_flat_row(result),
        },
    )
