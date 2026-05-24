"""HTTP error rendering — middleware + exception handlers.

Every failure that escapes a route lands here and is shaped into a uniform
:class:`ErrorEnvelope` JSON body. The handlers cover four axes:

* :class:`DomainError`        — application-defined failures (use case raised).
* :class:`HTTPException`      — fastapi / starlette signalled HTTP errors.
* :class:`RequestValidationError` — Pydantic / FastAPI input validation.
* :class:`Exception`          — anything else (programmer bug). Logged with
  a stack trace; the wire body never leaks the trace to the client.

Per-request correlation: :class:`RequestIdMiddleware` assigns a UUID to every
incoming request, binds it onto the structlog contextvars so every log event
during the request carries ``trace_id=…``, mirrors it into the response body
(``ErrorEnvelope.trace_id``) and the ``X-Request-ID`` header.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from typing import Final, override

import structlog
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.base import BaseHTTPMiddleware

from asmr_balance.logging import get_logger
from asmr_balance.web.dto import ErrorEnvelope
from asmr_balance.web.use_cases.errors import DomainError

_REQUEST_ID_HEADER: Final[str] = "X-Request-ID"
_log = get_logger(__name__)


def _new_trace_id() -> str:
    return uuid.uuid4().hex


def _trace_id_of(request: Request) -> str:
    """Return the request's trace_id (falling back to a fresh one if missing)."""
    return getattr(request.state, "trace_id", None) or _new_trace_id()


def _envelope_response(envelope: ErrorEnvelope) -> JSONResponse:
    return JSONResponse(
        status_code=envelope.status,
        content=envelope.model_dump(mode="json"),
        headers={_REQUEST_ID_HEADER: envelope.trace_id},
    )


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Bind a per-request UUID into structlog contextvars + response headers."""

    @override
    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        trace_id = request.headers.get(_REQUEST_ID_HEADER) or _new_trace_id()
        request.state.trace_id = trace_id
        structlog.contextvars.bind_contextvars(
            trace_id=trace_id,
            path=request.url.path,
            method=request.method,
        )
        try:
            response = await call_next(request)
        finally:
            structlog.contextvars.unbind_contextvars("trace_id", "path", "method")
        response.headers[_REQUEST_ID_HEADER] = trace_id
        return response


async def _domain_handler(request: Request, exc: DomainError) -> JSONResponse:
    trace_id = _trace_id_of(request)
    _log.warning(
        "domain_error",
        error=exc.__class__.__name__,
        detail=str(exc),
        status=exc.status_code,
        **exc.context,
    )
    envelope = ErrorEnvelope(
        error=exc.__class__.__name__,
        detail=str(exc),
        status=exc.status_code,
        context=exc.context,
        trace_id=trace_id,
    )
    return _envelope_response(envelope)


async def _http_exception_handler(
    request: Request,
    exc: StarletteHTTPException,
) -> JSONResponse:
    trace_id = _trace_id_of(request)
    _log.info(
        "http_exception",
        error="HTTPException",
        detail=str(exc.detail),
        status=exc.status_code,
    )
    envelope = ErrorEnvelope(
        error="HTTPException",
        detail=str(exc.detail),
        status=exc.status_code,
        context={},
        trace_id=trace_id,
    )
    return _envelope_response(envelope)


_STATUS_VALIDATION: Final[int] = 422
_STATUS_INTERNAL: Final[int] = 500


async def _validation_handler(
    request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    trace_id = _trace_id_of(request)
    errors = exc.errors()
    _log.warning(
        "request_validation_error",
        error="RequestValidationError",
        errors=errors,
        status=_STATUS_VALIDATION,
    )
    envelope = ErrorEnvelope(
        error="RequestValidationError",
        detail="request validation failed",
        status=_STATUS_VALIDATION,
        context={"errors": errors},
        trace_id=trace_id,
    )
    return _envelope_response(envelope)


async def _unhandled_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catch-all for non-domain exceptions — log the trace, hide it from clients."""
    trace_id = _trace_id_of(request)
    _log.exception(
        "unhandled_exception",
        error=exc.__class__.__name__,
        status=_STATUS_INTERNAL,
    )
    envelope = ErrorEnvelope(
        error=exc.__class__.__name__,
        detail="internal server error",
        status=_STATUS_INTERNAL,
        context={},
        trace_id=trace_id,
    )
    return _envelope_response(envelope)


def install_exception_handlers(app: FastAPI) -> None:
    """Install the request-id middleware and every exception handler on ``app``."""
    app.add_middleware(RequestIdMiddleware)
    app.add_exception_handler(DomainError, _domain_handler)
    app.add_exception_handler(StarletteHTTPException, _http_exception_handler)
    app.add_exception_handler(RequestValidationError, _validation_handler)
    app.add_exception_handler(Exception, _unhandled_handler)
