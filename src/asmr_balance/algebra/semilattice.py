"""Verdict — a bounded join-semilattice for diagnostic severity.

The verdict carrier set is the three-element total order ``OK < WARN < FAIL``
with the join operator ``⊔`` realized as ``__or__``. This satisfies the
semilattice axioms (associativity, commutativity, idempotence) and is bounded
by the bottom element ``OK`` (the identity of ``__or__``). The top element
``FAIL`` annihilates: ``x ⊔ FAIL = FAIL`` for all x.

We deliberately use :class:`enum.Enum`, **not** :class:`enum.StrEnum`. The
latter inherits :class:`int`'s bitwise ``__or__`` indirectly via integer
promotion and would yield undefined values when combined. Joining must be a
closed binary operation on the carrier; ``Enum`` with an explicit ``__or__``
enforces that statically.
"""

from __future__ import annotations

from enum import Enum
from functools import reduce
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable


class Verdict(Enum):
    """Bounded join-semilattice over diagnostic severity.

    Order: ``OK ⊑ WARN ⊑ FAIL``. Join (``|``) returns the maximum element,
    with ``OK`` as the identity (bottom).

    Example:
        >>> Verdict.OK | Verdict.WARN
        <Verdict.WARN: 1>
        >>> Verdict.WARN | Verdict.FAIL
        <Verdict.FAIL: 2>
        >>> Verdict.OK | Verdict.OK
        <Verdict.OK: 0>
    """

    OK = 0
    WARN = 1
    FAIL = 2

    def __or__(self, other: Verdict) -> Verdict:
        """Semilattice join (least upper bound).

        Returns the greater element under ``OK ⊑ WARN ⊑ FAIL``.
        """
        return self if self.value >= other.value else other

    @classmethod
    def bottom(cls) -> Verdict:
        """The identity of ``|``: the least element of the lattice."""
        return cls.OK

    @classmethod
    def top(cls) -> Verdict:
        """The annihilator of ``|``: the greatest element of the lattice."""
        return cls.FAIL

    @classmethod
    def join(cls, verdicts: Iterable[Verdict]) -> Verdict:
        """Fold a sequence of verdicts under ``|`` (``bottom()`` on empty input)."""
        return reduce(lambda a, b: a | b, verdicts, cls.bottom())
