from __future__ import annotations

from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.testclient import TestClient

_BOOM = "boom"
_TEAPOT_DETAIL = "i am a teapot"


def _explode_router() -> APIRouter:
    router = APIRouter()

    # pyright sees these inner handlers as unused — they are registered on
    # `router` by the decorator, mirroring the cli.py pattern for @app.callback.
    @router.get("/__raise_value_error")
    def _raise_value_error() -> None:  # pyright: ignore[reportUnusedFunction]
        raise ValueError(_BOOM)

    @router.get("/__raise_http")
    def _raise_http() -> None:  # pyright: ignore[reportUnusedFunction]
        raise HTTPException(status_code=418, detail=_TEAPOT_DETAIL)

    return router


def test_unhandled_exception_renders_500(app: FastAPI) -> None:
    app.include_router(_explode_router())
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/__raise_value_error")
    assert response.status_code == 500
    body = response.json()
    assert body["error"] == "ValueError"
    assert body["status"] == 500
    assert body["detail"] == "internal server error"
    assert body["trace_id"]
    assert response.headers["X-Request-ID"] == body["trace_id"]


def test_http_exception_renders_envelope(app: FastAPI) -> None:
    app.include_router(_explode_router())
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/__raise_http")
    assert response.status_code == 418
    body = response.json()
    assert body["error"] == "HTTPException"
    assert body["detail"] == "i am a teapot"
    assert body["status"] == 418
    assert body["context"] == {}


def test_validation_error_renders_envelope(client: TestClient) -> None:
    # POST /api/inspect with no multipart body triggers RequestValidationError.
    response = client.post("/api/inspect")
    assert response.status_code == 422
    body = response.json()
    assert body["error"] == "RequestValidationError"
    assert body["detail"] == "request validation failed"
    assert body["context"]["errors"]
    assert body["trace_id"]
