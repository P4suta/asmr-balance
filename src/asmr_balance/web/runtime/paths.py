"""Filesystem roots for the web layer.

Both are resolved on every call so tests can rebind via ``monkeypatch.setenv``
without restarting the app. Production defaults match the docker-compose
mount points (``/library:ro`` read-only, named volume ``web-reports:/app/reports``).
"""

from __future__ import annotations

import os
from pathlib import Path


def library_root() -> Path:
    """Mount point for the user's audio library (read-only)."""
    return Path(os.environ.get("ASMR_LIBRARY_ROOT", "/library"))


def reports_root() -> Path:
    """Per-job output directory root (writable)."""
    return Path(os.environ.get("ASMR_REPORTS_ROOT", "/app/reports"))
