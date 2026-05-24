"""Package-relative paths for templates and static assets.

Locating these via :func:`importlib.resources.files` keeps the web layer
independent of the wheel layout — installed source, editable install, and
in-container source-mount all resolve identically.
"""

from __future__ import annotations

from importlib.resources import files
from pathlib import Path
from typing import Final

_PKG_ROOT: Final[Path] = Path(str(files("asmr_balance.web")))

TEMPLATES_DIR: Final[Path] = _PKG_ROOT / "templates"
"""Jinja2 search root for HTMX templates."""

STATIC_DIR: Final[Path] = _PKG_ROOT / "static"
"""Mount point for ``/static`` (CSS / JS)."""
