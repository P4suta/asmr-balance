"""HTTP boundary for the inspect use case.

This module owns *only* the adaptation between HTTP and the
:func:`perform_inspect` use case: parse the upload, project the domain result
to the response shape each endpoint serves. Error translation is delegated to
the centralized handlers in :mod:`asmr_balance.web.errors`; this module never
catches use case exceptions itself.

Two response shapes share one use case:

- ``POST /api/inspect`` — JSON (Pydantic :class:`InspectResponse`).
- ``POST /api/inspect/partial`` — HTML (HTMX partial; template receives the
  same DTO plus a pre-flattened ``Mapping`` of dotted column names and any
  Plotly figure specs derived from the metric record).
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, File, Request, UploadFile
from fastapi.responses import HTMLResponse

from asmr_balance.config.model import Config
from asmr_balance.metrics.record import MetricRecord
from asmr_balance.scan.pipeline import FileResult
from asmr_balance.sink.base import result_to_flat_row
from asmr_balance.web.dto import INSPECT_ERROR_RESPONSES, InspectResponse
from asmr_balance.web.use_cases.inspect import perform_inspect
from asmr_balance.web.views import (
    band_imbalance_figure,
    sliding_delta_figure,
    true_peak_figure,
)

router = APIRouter(prefix="/api", tags=["inspect"])


async def _execute(file: UploadFile) -> tuple[FileResult, str]:
    """Read the upload and run the use case once."""
    audio_bytes = await file.read()
    result = perform_inspect(audio_bytes, file.filename)
    return result, file.filename or "(unnamed)"


def _figures_for(record: MetricRecord) -> dict[str, dict[str, Any]]:
    """Build the Plotly figure specs the inspect partial template renders.

    Returns an empty dict for SKIPPED / ERRORED records (no metrics to chart);
    the template guards on ``response.record.status == "analyzed"``.
    """
    figures: dict[str, dict[str, Any]] = {}
    thresholds = Config().thresholds
    if record.band is not None:
        figures["band"] = band_imbalance_figure(record.band, thresholds.band_bias).to_plotly_json()
    if record.dynamics is not None:
        figures["true_peak"] = true_peak_figure(
            record.dynamics, thresholds.true_peak_clip
        ).to_plotly_json()
    if record.sliding is not None:
        figures["sliding"] = sliding_delta_figure(record.sliding).to_plotly_json()
    return figures


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

    The template receives the wire DTO, a pre-materialized flat column view
    (presentation concern — kept out of the JSON wire format), and the
    Plotly figure specs for the inline chart sections.
    """
    result, source_name = await _execute(file)
    templates = request.app.state.templates
    return templates.TemplateResponse(
        request,
        "_inspect_result.html",
        {
            "response": InspectResponse.from_file_result(result, source_name=source_name),
            "flat": result_to_flat_row(result),
            "figures": _figures_for(result.record),
        },
    )
