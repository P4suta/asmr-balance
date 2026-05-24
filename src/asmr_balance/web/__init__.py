"""FastAPI-backed Web UI for asmr-balance.

The web layer is a thin shell over :mod:`asmr_balance.scan`; the analysis
pipeline stays unchanged. Run it with ``asmr-balance-web`` (uvicorn launcher)
or import :func:`asmr_balance.web.app.create_app` for embedding/testing.
"""

from __future__ import annotations

from asmr_balance.web.app import create_app

__all__ = ["create_app"]
