"""Test session setup: hypothesis profiles + structlog reset between tests."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

import hypothesis
import pytest
import structlog

if TYPE_CHECKING:
    from collections.abc import Iterator

hypothesis.settings.register_profile("dev", max_examples=50, deadline=None)
hypothesis.settings.register_profile("ci", max_examples=2000, deadline=None)
hypothesis.settings.load_profile(os.environ.get("HYPOTHESIS_PROFILE", "dev"))


@pytest.fixture(autouse=True)
def structlog_reset() -> Iterator[None]:
    """Restore structlog default config around every test."""
    structlog.reset_defaults()
    yield
    structlog.reset_defaults()
