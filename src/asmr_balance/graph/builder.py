"""Declarative builder for the signal graph.

Builder methods add filter or reducer nodes and return :class:`Stream` handles
(or ``None`` for terminal reducers). Re-binding the same :class:`Stream` to
multiple downstream consumers expresses *broadcast*: at scheduler time, the
producer pushes its emitted payloads to every child node.

Each filter method is a thin wrapper around a constructor from
:mod:`asmr_balance.nodes`; the wrapping exists to (a) keep node typing
internal to the graph layer and (b) make the wired-up DAG self-documenting
in pipeline call sites.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from asmr_balance.algebra.reducer import Reducer
from asmr_balance.graph.frozen import (
    FilterNode,
    FrozenGraph,
    Node,
    ReducerNode,
    SourceNode,
)
from asmr_balance.graph.types import (
    BandedBlock,
    Filter,
    KWeightedBlock,
    LowPassBlock,
    OversampledBlock,
    RawBlock,
    ShortTermZBlock,
    Stream,
    ZBlock,
)
from asmr_balance.nodes.bandsplit import BANDS, BandedFrame, BandSpec, ThirdOctaveBandSplit
from asmr_balance.nodes.kweighting import KWeightingFilter
from asmr_balance.nodes.lowpass import LowPassFilter
from asmr_balance.nodes.oversample import Oversample4xPolyphase
from asmr_balance.nodes.zblocks import ShortTermZBlocksFilter, ZBlocksFilter


@dataclass(slots=True)
class GraphBuilder:
    """Mutable graph builder. Call ``freeze()`` exactly once when wiring is done."""

    _nodes: list[Node] = field(default_factory=list)
    _children: dict[int, list[int]] = field(default_factory=lambda: defaultdict(list))
    _source_id: int | None = None
    _reducer_names: set[str] = field(default_factory=set)

    # ------------------------------------------------------------------
    # Source
    # ------------------------------------------------------------------
    def source(self) -> Stream[RawBlock]:
        """Register the single source node (must be called exactly once)."""
        if self._source_id is not None:
            msg = "GraphBuilder.source() may only be called once"
            raise ValueError(msg)
        node_id = self._next_id()
        self._nodes.append(SourceNode(node_id=node_id))
        self._source_id = node_id
        return Stream(node_id)

    # ------------------------------------------------------------------
    # Filter nodes
    # ------------------------------------------------------------------
    def kweight(self, raw: Stream[RawBlock], sample_rate: int) -> Stream[KWeightedBlock]:
        return self._add_filter(KWeightingFilter(sample_rate=sample_rate), parents=(raw,))

    def zblocks(self, kw: Stream[KWeightedBlock], sample_rate: int) -> Stream[ZBlock]:
        return self._add_filter(ZBlocksFilter(sample_rate=sample_rate), parents=(kw,))

    def shortterm_zblocks(
        self, kw: Stream[KWeightedBlock], sample_rate: int
    ) -> Stream[ShortTermZBlock]:
        return self._add_filter(ShortTermZBlocksFilter(sample_rate=sample_rate), parents=(kw,))

    def lowpass(
        self, raw: Stream[RawBlock], sample_rate: int, cutoff_hz: float = 300.0, order: int = 4
    ) -> Stream[LowPassBlock]:
        return self._add_filter(
            LowPassFilter(sample_rate=sample_rate, cutoff_hz=cutoff_hz, order=order),
            parents=(raw,),
        )

    def bandsplit(
        self,
        raw: Stream[RawBlock],
        sample_rate: int,
        bands: tuple[BandSpec, ...] = BANDS,
    ) -> Stream[BandedFrame]:
        return self._add_filter(
            ThirdOctaveBandSplit(sample_rate=sample_rate, bands=bands),
            parents=(raw,),
        )

    def oversample4x(self, raw: Stream[RawBlock]) -> Stream[OversampledBlock]:
        return self._add_filter(Oversample4xPolyphase(), parents=(raw,))

    # ------------------------------------------------------------------
    # Reducers — terminals
    # ------------------------------------------------------------------
    def reduce[T](self, name: str, reducer: Reducer[T, Any], input_stream: Stream[T]) -> None:
        """Register a terminal reducer consuming ``input_stream``.

        ``name`` is the key under which the reducer's :meth:`finalize` output
        will appear in the scheduler's result mapping. Names must be unique
        within one graph.
        """
        if name in self._reducer_names:
            msg = f"reducer name {name!r} already registered"
            raise ValueError(msg)
        self._reducer_names.add(name)
        node_id = self._next_id()
        node = ReducerNode(node_id=node_id, op=reducer, name=name, parents=(input_stream.node_id,))
        self._nodes.append(node)
        self._children[input_stream.node_id].append(node_id)

    # ------------------------------------------------------------------
    # Freeze — topological sort and validation
    # ------------------------------------------------------------------
    def freeze(self) -> FrozenGraph:
        """Produce an immutable execution plan (Kahn topological sort)."""
        if self._source_id is None:
            msg = "GraphBuilder.freeze() requires a source node"
            raise ValueError(msg)

        in_degree: dict[int, int] = {n.node_id: _parent_count(n) for n in self._nodes}
        ready: list[int] = [nid for nid, d in in_degree.items() if d == 0]
        topo: list[int] = []
        while ready:
            nid = ready.pop(0)
            topo.append(nid)
            for child in self._children.get(nid, ()):
                in_degree[child] -= 1
                if in_degree[child] == 0:
                    ready.append(child)
        if len(topo) != len(self._nodes):
            msg = "graph contains a cycle (Kahn topological sort failed)"
            raise ValueError(msg)

        return FrozenGraph(
            nodes=tuple(self._nodes),
            topo=tuple(topo),
            children=tuple(
                tuple(self._children.get(nid, ())) for nid in range(len(self._nodes))
            ),
            reducer_ids=tuple(n.node_id for n in self._nodes if isinstance(n, ReducerNode)),
        )

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    def _next_id(self) -> int:
        return len(self._nodes)

    def _add_filter[InP, OutP](
        self, op: Filter[InP, OutP], parents: Iterable[Stream[InP]]
    ) -> Stream[OutP]:
        parents_t = tuple(parents)
        if not parents_t:
            msg = "filter node requires at least one parent stream"
            raise ValueError(msg)
        node_id = self._next_id()
        parent_ids = tuple(p.node_id for p in parents_t)
        self._nodes.append(FilterNode(node_id=node_id, op=op, parents=parent_ids))
        for pid in parent_ids:
            self._children[pid].append(node_id)
        return Stream(node_id)


def _parent_count(n: Node) -> int:
    match n:
        case SourceNode():
            return 0
        case FilterNode():
            return len(n.parents)
        case ReducerNode():
            return len(n.parents)
