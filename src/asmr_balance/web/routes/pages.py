"""HTML pages served via Jinja2 templates."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

router = APIRouter(tags=["pages"])


@router.get("/", response_class=HTMLResponse)
def index(request: Request) -> HTMLResponse:
    """Render the index page (Inspect tab in Phase 1a)."""
    templates = request.app.state.templates
    return templates.TemplateResponse(request, "index.html", {})
