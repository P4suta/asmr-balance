"""FastAPI application factory.

The factory wires together: package resources (templates + static), domain
routes (health, schema, inspect, library, scan, pages), the per-app
:class:`JobRegistry`, and global exception handlers. The returned
:class:`FastAPI` instance is fully self-contained — embed it in tests or
behind ASGI servers identically.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from asmr_balance import __version__
from asmr_balance.web.errors import install_exception_handlers
from asmr_balance.web.resources import STATIC_DIR, TEMPLATES_DIR
from asmr_balance.web.routes import health, inspect, library, pages, scan, schema
from asmr_balance.web.runtime.jobs import JobRegistry


def create_app() -> FastAPI:
    """Build a fresh :class:`FastAPI` instance wired with routes + templates."""
    app = FastAPI(
        title="asmr-balance",
        description="Multi-axis L/R balance scanner — Web UI",
        version=__version__,
    )
    app.state.templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
    app.state.job_registry = JobRegistry()
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
    app.include_router(health.router)
    app.include_router(schema.router)
    app.include_router(inspect.router)
    app.include_router(library.router)
    app.include_router(scan.router)
    app.include_router(pages.router)
    install_exception_handlers(app)
    return app
