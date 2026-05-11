"""Unit tests for :class:`asmr_balance.algebra.semilattice.Verdict`."""

from __future__ import annotations

import pytest

from asmr_balance.algebra.semilattice import Verdict


def test_order_is_total_ok_warn_fail() -> None:
    assert Verdict.OK.value < Verdict.WARN.value < Verdict.FAIL.value


@pytest.mark.parametrize(
    ("a", "b", "expected"),
    [
        (Verdict.OK, Verdict.OK, Verdict.OK),
        (Verdict.OK, Verdict.WARN, Verdict.WARN),
        (Verdict.WARN, Verdict.OK, Verdict.WARN),
        (Verdict.WARN, Verdict.WARN, Verdict.WARN),
        (Verdict.WARN, Verdict.FAIL, Verdict.FAIL),
        (Verdict.FAIL, Verdict.WARN, Verdict.FAIL),
        (Verdict.FAIL, Verdict.FAIL, Verdict.FAIL),
        (Verdict.OK, Verdict.FAIL, Verdict.FAIL),
    ],
)
def test_join_truth_table(a: Verdict, b: Verdict, expected: Verdict) -> None:
    assert a | b == expected


def test_bottom_is_ok() -> None:
    assert Verdict.bottom() is Verdict.OK


def test_top_is_fail() -> None:
    assert Verdict.top() is Verdict.FAIL


def test_join_empty_iterable_returns_bottom() -> None:
    assert Verdict.join([]) is Verdict.OK


def test_join_singleton_returns_element() -> None:
    assert Verdict.join([Verdict.WARN]) is Verdict.WARN


def test_join_aggregates_max() -> None:
    assert Verdict.join([Verdict.OK, Verdict.WARN, Verdict.FAIL, Verdict.OK]) is Verdict.FAIL


def test_join_iterator_input_consumed_once() -> None:
    iterator = iter([Verdict.WARN, Verdict.OK, Verdict.WARN])
    assert Verdict.join(iterator) is Verdict.WARN
    assert list(iterator) == []
