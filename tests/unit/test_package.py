"""Smoke tests for the top-level package."""

from __future__ import annotations

import asmr_balance


def test_version_is_string() -> None:
    assert isinstance(asmr_balance.__version__, str)


def test_version_components_are_digits() -> None:
    parts = asmr_balance.__version__.split(".")
    assert len(parts) == 3
    for part in parts:
        assert part.isdigit()


def test_all_exports() -> None:
    assert "__version__" in asmr_balance.__all__
