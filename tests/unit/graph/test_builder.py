"""Tests for :mod:`asmr_balance.graph.builder`."""

from __future__ import annotations

import pytest

from asmr_balance.graph.builder import GraphBuilder
from asmr_balance.graph.frozen import FilterNode, ReducerNode, SourceNode
from asmr_balance.metrics.loudness import IntegratedLoudnessReducer


def test_source_must_be_called_first() -> None:
    g = GraphBuilder()
    raw = g.source()
    assert raw.node_id == 0


def test_source_can_only_be_called_once() -> None:
    g = GraphBuilder()
    g.source()
    with pytest.raises(ValueError, match="once"):
        g.source()


def test_freeze_requires_source() -> None:
    g = GraphBuilder()
    with pytest.raises(ValueError, match="requires a source"):
        g.freeze()


def test_minimal_graph_freezes_with_source_and_one_reducer() -> None:
    g = GraphBuilder()
    raw = g.source()
    kw = g.kweight(raw, sample_rate=48000)
    z = g.zblocks(kw, sample_rate=48000)
    g.reduce("loudness", IntegratedLoudnessReducer(), z)
    frozen = g.freeze()
    assert len(frozen.nodes) == 4
    assert isinstance(frozen.nodes[0], SourceNode)
    assert isinstance(frozen.nodes[1], FilterNode)
    assert isinstance(frozen.nodes[2], FilterNode)
    assert isinstance(frozen.nodes[3], ReducerNode)
    # Reducer comes last in topo (no children).
    assert frozen.topo[-1] == 3
    assert frozen.reducer_ids == (3,)


def test_duplicate_reducer_name_rejected() -> None:
    g = GraphBuilder()
    raw = g.source()
    kw = g.kweight(raw, sample_rate=48000)
    z = g.zblocks(kw, sample_rate=48000)
    g.reduce("loudness", IntegratedLoudnessReducer(), z)
    with pytest.raises(ValueError, match="already registered"):
        g.reduce("loudness", IntegratedLoudnessReducer(), z)


def test_broadcast_via_shared_stream_handle() -> None:
    """Same Stream handle used twice creates two children of one producer."""
    g = GraphBuilder()
    raw = g.source()
    kw = g.kweight(raw, sample_rate=48000)
    z = g.zblocks(kw, sample_rate=48000)
    # Two reducers consuming the same z stream → broadcast.
    g.reduce("a", IntegratedLoudnessReducer(), z)
    g.reduce("b", IntegratedLoudnessReducer(), z)
    frozen = g.freeze()
    # zblocks node id should be 2; it should have two children (3 and 4).
    z_node_id = z.node_id
    assert sorted(frozen.children[z_node_id]) == [3, 4]


def test_topological_order_respects_dependencies() -> None:
    g = GraphBuilder()
    raw = g.source()
    kw = g.kweight(raw, sample_rate=48000)
    z = g.zblocks(kw, sample_rate=48000)
    g.reduce("loudness", IntegratedLoudnessReducer(), z)
    frozen = g.freeze()
    positions = {nid: idx for idx, nid in enumerate(frozen.topo)}
    # raw must come before kw, kw before z, z before reducer.
    assert positions[raw.node_id] < positions[kw.node_id]
    assert positions[kw.node_id] < positions[z.node_id]


def test_stream_equality_by_node_id() -> None:
    from asmr_balance.graph.types import Stream

    a = Stream(node_id=5)
    b = Stream(node_id=5)
    c = Stream(node_id=6)
    assert a == b
    assert a != c
    assert hash(a) == hash(b)
