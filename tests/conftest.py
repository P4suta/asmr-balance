"""Top-level pytest configuration.

Registers the project-specific Hypothesis profiles and shared fixtures. Mirrors
the configuration that ``tests/legacy/conftest.py`` provided for the legacy
suite (kept for parity).
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from hypothesis import HealthCheck, Phase, settings

if TYPE_CHECKING:
    import pytest

# ----------------------------------------------------------------------
# Hypothesis profiles
# ----------------------------------------------------------------------
settings.register_profile(
    "dev",
    max_examples=50,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
    print_blob=True,
)
settings.register_profile(
    "ci",
    max_examples=2000,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
    phases=(Phase.generate, Phase.target, Phase.shrink),
    print_blob=True,
)

_profile = os.environ.get("HYPOTHESIS_PROFILE", "dev")
settings.load_profile(_profile)


def pytest_report_header() -> list[str]:
    """Emit the active Hypothesis profile to the pytest banner."""
    return [f"hypothesis profile: {_profile}"]


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:  # noqa: ARG001
    """Placeholder hook — no modifications yet; kept as a marker for future use."""
    return
