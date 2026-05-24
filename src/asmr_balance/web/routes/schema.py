"""Canonical column-name schema endpoint."""

from __future__ import annotations

from fastapi import APIRouter

from asmr_balance.sink.base import COLUMN_NAMES
from asmr_balance.web.dto import SchemaResponse

router = APIRouter(prefix="/api", tags=["schema"])


@router.get("/schema", response_model=SchemaResponse)
def get_schema() -> SchemaResponse:
    """Return the canonical dotted column-name tuple."""
    return SchemaResponse(columns=COLUMN_NAMES)
