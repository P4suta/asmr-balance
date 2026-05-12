"""Stage-typed payloads and Filter protocol for the signal DAG.

Every distinct ``stage`` of the pipeline has its own :class:`typing.NewType`
alias. This is more than aesthetics: it lets ``basedpyright`` reject a
``Stream[RawBlock]`` being plugged into a reducer that expects
``Stream[ZBlock]`` — a class of error that the legacy ``Analyzer`` protocol's
single ``StereoBlock`` input could not catch.

The :class:`Stream` value is an opaque handle issued by the graph builder
(see :mod:`asmr_balance.graph.builder`). It carries the producing node id
only; the actual payloads flow through the scheduler's frontier slots.

Two stage values are typed as ``tuple[float, float]`` rather than ndarrays:
:data:`ZBlock` (one 400 ms K-weighted mean-square per channel) and
:data:`ShortTermZBlock` (one 3 s mean-square per channel). They are emitted
one at a time per hop and per-block stats are kept by reducers downstream.
"""

from __future__ import annotations

from typing import NewType, Protocol, override

import numpy as np
from numpy.typing import NDArray

# ---------------------------------------------------------------------------
# Stage-typed payloads
# ---------------------------------------------------------------------------
RawBlock = NewType("RawBlock", NDArray[np.float32])
"""Stereo PCM block produced by :mod:`asmr_balance.source.open`. Shape ``(N, 2)``,
contiguous, ``float32``, sample-rate-native."""

KWeightedBlock = NewType("KWeightedBlock", NDArray[np.float64])
"""K-weighted stereo block (BS.1770-5 pre-filter applied). Shape ``(N, 2)``,
``float64`` because BS.1770 measurement is float64-internal."""

ZBlock = NewType("ZBlock", tuple[float, float])
"""One 400 ms / 100 ms-hop K-weighted mean-square pair ``(z_L, z_R)``. Emitted
once per hop after the first full window is buffered."""

ShortTermZBlock = NewType("ShortTermZBlock", tuple[float, float])
"""One 3 s / 100 ms-hop K-weighted mean-square pair, used by the EBU R128
loudness-range (LRA) reducer."""

LowPassBlock = NewType("LowPassBlock", NDArray[np.float64])
"""Low-pass-filtered stereo block (``< 300 Hz``). Shape ``(N, 2)``, shared by
the low-band phase-coherence reducer and the band-imbalance low-band slot."""

BandedBlock = NewType("BandedBlock", NDArray[np.float64])
"""A single-band-passed stereo block. Shape ``(N, 2)``."""

OversampledBlock = NewType("OversampledBlock", NDArray[np.float64])
"""4x polyphase-oversampled stereo block (BS.1770-5 Annex 2). Shape ``(4N, 2)``."""


# ---------------------------------------------------------------------------
# Stream handle (graph identity only — no payload storage)
# ---------------------------------------------------------------------------
class Stream[T]:
    """Opaque handle for an edge in the graph.

    Stream values are issued by :class:`~asmr_balance.graph.builder.GraphBuilder`
    and consumed by ``.reduce()`` or further filter calls. Two consumers
    sharing the same ``Stream`` instance receive *broadcasts* of the same
    payloads from the scheduler.

    The generic parameter ``T`` is the stage payload type (e.g. ``ZBlock``).
    Stream values are never compared structurally — equality is by node id —
    so a fresh ``g.kweight(raw)`` call always produces a fresh logical edge
    even if the SOS coefficients are identical.
    """

    __slots__ = ("_node_id",)

    def __init__(self, node_id: int) -> None:
        self._node_id = node_id

    @property
    def node_id(self) -> int:
        """The producing node id within the graph builder."""
        return self._node_id

    @override
    def __repr__(self) -> str:
        return f"Stream(node_id={self._node_id})"

    @override
    def __eq__(self, other: object) -> bool:
        return isinstance(other, Stream) and self._node_id == other._node_id

    @override
    def __hash__(self) -> int:
        return hash(("Stream", self._node_id))


# ---------------------------------------------------------------------------
# Filter protocol — Mealy stream transformer (stateful, sequential)
# ---------------------------------------------------------------------------
class Filter[InP, OutP](Protocol):
    """Mealy stream transformer: stateful, sequential, ``In → list[Out]``.

    Filters are *not* monoids: their per-sample state is path-dependent
    (e.g. IIR delay lines). This is why intra-file chunk parallelism is
    forbidden (the IIR ``zi`` cannot be merged across an arbitrary split).

    Implementations may emit any number of output payloads per input call
    (including zero, for windowed filters that accumulate before emitting).
    The :meth:`flush` method is invoked exactly once at end-of-stream so that
    partial windows can be drained or discarded.
    """

    def process(self, payload: InP) -> list[OutP]:
        """Consume one payload and return zero or more downstream payloads."""
        ...

    def flush(self) -> list[OutP]:
        """Drain any internal buffer at end-of-stream and return final emissions."""
        ...
