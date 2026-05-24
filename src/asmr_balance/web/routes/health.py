"""Liveness probe."""

from __future__ import annotations

from fastapi import APIRouter

from asmr_balance import __version__
from asmr_balance.web.dto import HealthResponse

router = APIRouter(tags=["meta"])


@router.get("/healthz", response_model=HealthResponse)
def healthz() -> HealthResponse:
    """Return the package version and a static ``ok`` status."""
    return HealthResponse(status="ok", version=__version__)
