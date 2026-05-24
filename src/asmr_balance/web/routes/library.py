"""Library browsing endpoints.

The web layer's view onto the read-only ``/library`` mount. The use case
:func:`list_library` raises :class:`LibraryPathError` for every "outside the
mount / not found / not a directory" path; the centralized handler in
:mod:`asmr_balance.web.errors` converts those into 404 envelopes uniformly.
"""

from __future__ import annotations

from pathlib import PurePosixPath
from typing import Annotated

from fastapi import APIRouter, Query

from asmr_balance.web.dto import COMMON_ERROR_RESPONSES, LibraryEntryDto, LibraryListing
from asmr_balance.web.use_cases.library import list_library

router = APIRouter(prefix="/api", tags=["library"])


def _parent_of(rel_path: str) -> str | None:
    if not rel_path:
        return None
    parent = PurePosixPath(rel_path).parent
    return "" if str(parent) == "." else str(parent)


@router.get(
    "/library",
    response_model=LibraryListing,
    responses=COMMON_ERROR_RESPONSES,
)
def get_library(
    path: Annotated[str, Query(description="rel-path under /library; empty ⇒ root")] = "",
) -> LibraryListing:
    """List entries directly under ``path`` (no recursion)."""
    entries = list_library(path)
    return LibraryListing(
        rel_path=path,
        parent_rel_path=_parent_of(path),
        entries=tuple(LibraryEntryDto.from_entry(e) for e in entries),
    )
