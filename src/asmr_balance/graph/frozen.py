"""Frozen execution plan for the signal graph.

After :class:`GraphBuilder.freeze` runs Kahn's algorithm on the registered
nodes, the result is a :class:`FrozenGraph`: an immutable, topologically-ordered
description of *what to execute* and *in what order*. The scheduler
(:mod:`asmr_balance.graph.scheduler`) consumes this plan.

Nodes form an algebraic sum :data:`Node = SourceNode | FilterNode | ReducerNode`.
The discriminated union enables exhaustive ``match`` dispatch in the
scheduler, which ``basedpyright`` validates via ``assert_never``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, TypeAlias

from asmr_balance.algebra.reducer import Reducer
from asmr_balance.graph.types import Filter


@dataclass(frozen=True, slots=True)
class SourceNode:
    """The root of every graph — the entry point for ``RawBlock`` payloads."""

    node_id: int


@dataclass(frozen=True, slots=True)
class FilterNode:
    """A streaming transformer ``In → list[Out]`` with optional end-of-stream drain."""

    node_id: int
    op: Filter[Any, Any]
    parents: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class ReducerNode:
    """A terminal reducer that ingests payloads and produces one metric subtree."""

    node_id: int
    op: Reducer[Any, Any]
    name: str
    parents: tuple[int, ...]


Node: TypeAlias = SourceNode | FilterNode | ReducerNode


@dataclass(frozen=True, slots=True)
class FrozenGraph:
    """Immutable execution plan.

    Attributes:
        nodes: All nodes in registration order (node id == index).
        topo: Kahn-sorted topological order.
        children: ``children[i]`` is the tuple of downstream node ids for node ``i``.
        reducer_ids: Subset of node ids that are :class:`ReducerNode`.
    """

    nodes: tuple[Node, ...]
    topo: tuple[int, ...]
    children: tuple[tuple[int, ...], ...]
    reducer_ids: tuple[int, ...]

    def node_name(self, node_id: int) -> str | None:
        """Reducer name (or ``None`` for source / filter nodes)."""
        n = self.nodes[node_id]
        if isinstance(n, ReducerNode):
            return n.name
        return None
