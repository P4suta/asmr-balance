"""Edge-case formatting tests for :func:`asmr_balance.sink.html._fmt`."""

from __future__ import annotations

import math

from asmr_balance.sink.html import _fmt


def test_fmt_none_returns_dash() -> None:
    assert _fmt(None) == "—"


def test_fmt_nan_returns_nan_string() -> None:
    assert _fmt(math.nan) == "NaN"


def test_fmt_positive_infinity() -> None:
    assert _fmt(math.inf) == "+∞"


def test_fmt_negative_infinity() -> None:
    assert _fmt(-math.inf) == "−∞"


def test_fmt_normal_float() -> None:
    assert _fmt(3.14159) == "3.14"


def test_fmt_int_is_formatted() -> None:
    # Integers route through the float format spec.
    assert _fmt(42) == "42.00"
