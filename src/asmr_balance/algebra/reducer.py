"""Streaming reducer protocol.

A :class:`Reducer` consumes a typed stream of payloads and ultimately produces
exactly one *metric subtree* (a frozen pydantic record from
:mod:`asmr_balance.metrics.subtrees`). The protocol is intentionally minimal:

* ``update(payload)`` ingests one payload of stage type ``In`` and mutates the
  reducer's internal state.
* ``finalize()`` produces the metric subtree of type ``M`` once the stream
  has ended (the scheduler calls it exactly once per scan).

The reducer is *not* required to be a monoid. The current execution model is a
sequential push-style scheduler (see :mod:`asmr_balance.graph.scheduler`) over a
single file. File-level parallelism is achieved by running independent
reducers in separate processes (see :mod:`asmr_balance.scan.parallel`), so an
associative ``merge`` is unnecessary today. If future work demands intra-file
chunk parallelism, a :class:`MergeableReducer` subprotocol can be added; this
is intentionally deferred (YAGNI).

The protocol is generic over both the input stage type and the output metric
type so that schema introspection can recover the typed subtree at build time
without runtime string keys.
"""

from __future__ import annotations

from typing import ClassVar, Protocol, runtime_checkable


@runtime_checkable
class Reducer[In, M](Protocol):
    """A streaming reducer from ``Stream[In]`` to a typed metric subtree ``M``.

    Implementations carry internal state and are *not* thread-safe. The
    scheduler guarantees a strict ``update*`` then exactly-one ``finalize``
    call sequence; behavior after ``finalize`` is undefined.

    Attributes:
        name: Symbolic identifier used for telemetry / log fields.
    """

    name: ClassVar[str]

    def update(self, payload: In) -> None:
        """Ingest one streaming payload.

        Args:
            payload: Stage-typed value (e.g. ``ZBlock``, ``KWeightedBlock``).
        """
        ...

    def finalize(self) -> M:
        """Produce the final metric subtree.

        This method is called exactly once. Implementations must remain pure
        with respect to ``self`` after returning, i.e. callers are free to
        discard the reducer immediately.
        """
        ...
