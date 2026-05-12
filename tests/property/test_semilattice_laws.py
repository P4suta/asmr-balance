"""Hypothesis property tests for :class:`Verdict` semilattice laws.

Verifies the three axioms (associativity, commutativity, idempotence) plus
the identity property of :meth:`Verdict.bottom` and the annihilator property
of :meth:`Verdict.top`.
"""

from __future__ import annotations

import pytest
from hypothesis import given, strategies as st

from asmr_balance.algebra.semilattice import Verdict

pytestmark = pytest.mark.property

_verdicts = st.sampled_from(list(Verdict))


@given(a=_verdicts, b=_verdicts, c=_verdicts)
def test_join_is_associative(a: Verdict, b: Verdict, c: Verdict) -> None:
    assert (a | b) | c == a | (b | c)


@given(a=_verdicts, b=_verdicts)
def test_join_is_commutative(a: Verdict, b: Verdict) -> None:
    assert a | b == b | a


@given(a=_verdicts)
def test_join_is_idempotent(a: Verdict) -> None:
    assert a | a == a


@given(a=_verdicts)
def test_bottom_is_identity(a: Verdict) -> None:
    assert a | Verdict.bottom() == a
    assert Verdict.bottom() | a == a


@given(a=_verdicts)
def test_top_is_annihilator(a: Verdict) -> None:
    assert a | Verdict.top() == Verdict.top()
    assert Verdict.top() | a == Verdict.top()
