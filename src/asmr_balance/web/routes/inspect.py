"""HTTP boundary for the inspect use case.

This module owns *only* the adaptation between HTTP and the
:func:`perform_inspect` use case: parse the upload, project the domain result
to the response shape each endpoint serves. Error translation is delegated to
the centralized handlers in :mod:`asmr_balance.web.errors`; this module never
catches use case exceptions itself — *except* on the NDJSON stream endpoint,
where the response status has already been written by the time a domain
failure surfaces and the only way to inform the client is an in-band
``InspectFailedEvent`` frame.

Three response shapes share one use case:

- ``POST /api/inspect``         — JSON (Pydantic :class:`InspectResponse`).
- ``POST /api/inspect/partial`` — HTML (HTMX partial; one-shot, full page render).
- ``POST /api/inspect/stream``  — NDJSON stream: progress frames pushed as the
  pipeline advances, plus a final ``done`` (with pre-rendered HTML) or
  ``failed`` frame. Designed for ``fetch()`` + ``ReadableStream`` consumers.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated, Any

from fastapi import APIRouter, File, Request, UploadFile
from fastapi.responses import HTMLResponse, StreamingResponse

from asmr_balance.config.model import Config
from asmr_balance.metrics.record import MetricRecord
from asmr_balance.scan.pipeline import FileResult
from asmr_balance.sink.base import result_to_flat_row
from asmr_balance.web.dto import (
    INSPECT_ERROR_RESPONSES,
    InspectDoneEvent,
    InspectFailedEvent,
    InspectProgressEvent,
    InspectResponse,
)
from asmr_balance.web.use_cases.errors import DomainError
from asmr_balance.web.use_cases.inspect import perform_inspect, perform_inspect_streaming
from asmr_balance.web.views import (
    band_imbalance_figure,
    derive_inspect_insights,
    diagnose,
    sliding_delta_figure,
    true_peak_figure,
)

router = APIRouter(prefix="/api", tags=["inspect"])

NDJSON_MEDIA_TYPE = "application/x-ndjson"


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


def _render_result_html(request: Request, result: FileResult, *, source_name: str) -> str:
    """Render the result-card partial to a string (no Response wrapping)."""
    templates = request.app.state.templates
    return templates.get_template("_inspect_result.html").render(
        request=request,
        response=InspectResponse.from_file_result(result, source_name=source_name),
        flat=result_to_flat_row(result),
        figures=_figures_for(result.record),
        diagnosis=diagnose(result),
        insights=derive_inspect_insights(result.record),
    )


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
    return HTMLResponse(_render_result_html(request, result, source_name=source_name))


@router.post(
    "/inspect/stream",
    responses=INSPECT_ERROR_RESPONSES,
)
async def inspect_stream(
    request: Request,
    file: Annotated[UploadFile, File()],
) -> StreamingResponse:
    """NDJSON stream — one JSON object per line, terminated by ``done`` or ``failed``.

    Frames (all carry a ``type`` discriminator):

    * ``progress`` — :class:`InspectProgressEvent`, ticked at every stage and
      every analyze block.
    * ``done``     — :class:`InspectDoneEvent` carrying the rendered HTML partial
      ready to inject. Last frame on the success path.
    * ``failed``   — :class:`InspectFailedEvent` on any failure. Last frame
      on the failure path.

    Once we return :class:`StreamingResponse` the HTTP 200 is already
    committed, so every failure — domain or otherwise — must surface as a
    ``failed`` frame rather than an HTTP status. This keeps the client
    contract beautifully uniform: ``fetch → for await frame → dispatch on
    frame.type``. No mid-stream status-code reasoning, no try/catch around
    the loop body. Unsupported suffix, decode failure, programmer bug — all
    come back as the same shape.
    """
    audio_bytes = await file.read()
    filename = file.filename

    async def frames() -> AsyncIterator[bytes]:
        try:
            async for event in perform_inspect_streaming(audio_bytes, filename):
                if isinstance(event, InspectProgressEvent):
                    yield (event.model_dump_json() + "\n").encode("utf-8")
                else:
                    # event: FileResult — render and emit terminal done frame.
                    source_name = filename or "(unnamed)"
                    html = _render_result_html(request, event, source_name=source_name)
                    yield (InspectDoneEvent(html=html).model_dump_json() + "\n").encode("utf-8")
        except DomainError as exc:
            failed = InspectFailedEvent(
                error=exc.__class__.__name__,
                detail=str(exc),
                status=exc.status_code,
                context=exc.context,
            )
            yield (failed.model_dump_json() + "\n").encode("utf-8")
        except Exception as exc:  # noqa: BLE001  -- unified failure framing
            # Unknown failures still need to leave the stream cleanly.
            # The router-level structlog handler logs the trace separately;
            # here we only shape the wire frame and never leak the message.
            failed = InspectFailedEvent(
                error=exc.__class__.__name__,
                detail="internal server error",
                status=500,
                context={},
            )
            yield (failed.model_dump_json() + "\n").encode("utf-8")

    return StreamingResponse(frames(), media_type=NDJSON_MEDIA_TYPE)
