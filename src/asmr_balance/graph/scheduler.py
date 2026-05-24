"""Push-style Kahn scheduler over a :class:`FrozenGraph`.

The scheduler is a tiny interpreter for the data-flow DAG: each tick consumes
a :class:`RawBlock` from the source, drives the topological order so every
node consumes its frontier and pushes outputs to children, then at end-of-stream
calls each filter's :meth:`flush` so partial windowed buffers can be drained.
At the very end, every :class:`ReducerNode` is :meth:`finalize`d and the
keyed results are returned.

The scheduler has no opinions about what reducers do — it only knows the
node algebra ``Source | Filter | Reducer`` and dispatches via exhaustive
``match``. New filter or reducer kinds can be added without touching the
scheduler.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, assert_never

from asmr_balance.graph.frozen import FilterNode, FrozenGraph, ReducerNode, SourceNode
from asmr_balance.graph.types import RawBlock
from asmr_balance.source.adt import Source
from asmr_balance.source.open import iter_blocks

BlockCallback = Callable[[int, int], None]
"""``(blocks_processed, total_blocks)`` ticked once per pulled :class:`RawBlock`."""


def run(
    graph: FrozenGraph,
    source: Source,
    *,
    on_block: BlockCallback | None = None,
    total_blocks: int = 0,
) -> dict[str, Any]:
    """Execute ``graph`` over the block stream from ``source``.

    Returns a mapping ``name → finalize() output`` for every
    :class:`ReducerNode` in the graph.

    Args:
        graph: frozen DAG to drive.
        source: stereo PCM stream wrapper.
        on_block: optional callback invoked after every consumed block. The
            callback receives ``(blocks_done, total_blocks)``; the streaming
            inspect endpoint uses this to emit NDJSON progress frames.
        total_blocks: caller-provided expected block count (used only as the
            second arg to ``on_block``; the loop itself doesn't depend on it).
    """
    n_nodes = len(graph.nodes)
    pending: list[list[Any]] = [[] for _ in range(n_nodes)]
    source_id = _find_source_id(graph)

    # Run phase — feed one block per tick and drive the graph to quiescence.
    # ``start=1`` because we want the count of *completed* blocks after _drive.
    blocks_done = 0
    for blocks_done, raw in enumerate(iter_blocks(source), start=1):
        pending[source_id].append(raw)
        _drive(graph, pending)
        if on_block is not None:
            on_block(blocks_done, total_blocks)

    # Flush phase — terminal drain.
    _flush(graph, pending)

    # Finalize reducers.
    results: dict[str, Any] = {}
    for nid in graph.reducer_ids:
        node = graph.nodes[nid]
        assert isinstance(node, ReducerNode)  # narrowing for type checkers
        results[node.name] = node.op.finalize()
    return results


def _find_source_id(graph: FrozenGraph) -> int:
    for node in graph.nodes:
        if isinstance(
            node, SourceNode
        ):  # pragma: no branch -- always at index 0 in canonical graphs
            return node.node_id
    msg = "FrozenGraph has no SourceNode"
    raise ValueError(msg)


def _drive(graph: FrozenGraph, pending: list[list[Any]]) -> None:  # noqa: C901  -- exhaustive match dispatch
    """One topological sweep: every node consumes its frontier and pushes outputs."""
    for nid in graph.topo:
        payloads = pending[nid]
        if not payloads:
            continue
        pending[nid] = []
        node = graph.nodes[nid]
        children = graph.children[nid]
        match node:
            case SourceNode():
                for payload in payloads:
                    for child in children:
                        pending[child].append(payload)
            case FilterNode():
                for payload in payloads:
                    for out in node.op.process(payload):
                        for child in children:
                            pending[child].append(out)
            case ReducerNode():
                for payload in payloads:
                    node.op.update(payload)
            case _:  # pragma: no cover -- exhaustive match safety net
                assert_never(node)


def _flush(graph: FrozenGraph, pending: list[list[Any]]) -> None:
    """Drain each filter in topological order and propagate any residual outputs.

    All current filters return an empty list from :meth:`flush` (their windows
    are anchored to the input stream and have nothing to spill at EOS). The
    propagation branch is kept for future filters with partial-window flushes.
    """
    for nid in graph.topo:
        node = graph.nodes[nid]
        if not isinstance(node, FilterNode):
            continue
        residual = node.op.flush()
        if not residual:
            continue
        for out in residual:  # pragma: no cover  -- exercised when a future filter emits at flush
            for child in graph.children[nid]:
                pending[child].append(out)
        _drive(graph, pending)  # pragma: no cover  -- paired with the above


def run_from_iter(graph: FrozenGraph, raw_blocks: list[RawBlock]) -> dict[str, Any]:
    """Variant of :func:`run` that drives the graph from an in-memory block list.

    Used by tests that bypass file I/O.
    """
    n_nodes = len(graph.nodes)
    pending: list[list[Any]] = [[] for _ in range(n_nodes)]
    source_id = _find_source_id(graph)
    for raw in raw_blocks:
        pending[source_id].append(raw)
        _drive(graph, pending)
    _flush(graph, pending)
    results: dict[str, Any] = {}
    for nid in graph.reducer_ids:
        node = graph.nodes[nid]
        assert isinstance(node, ReducerNode)
        results[node.name] = node.op.finalize()
    return results
