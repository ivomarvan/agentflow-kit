"""Unit tests for topology.py — Transition, Parallel, StateGraph."""

from __future__ import annotations

import enum
from typing import Any

import pytest

from src.agentflow.statemachine.context import Context
from src.agentflow.statemachine.resolver import VertexResolver
from src.agentflow.statemachine.topology import Parallel, StateGraph, Transition
from src.agentflow.statemachine.vertex import StateVertex

# ---------------------------------------------------------------------------
# Minimal concrete vertices for testing — FakeVertex (T070) not yet available.
# ---------------------------------------------------------------------------


class _AVertex(StateVertex):
    async def run(self, state: object, ctx: Context) -> tuple[Any, Any]:
        return (object(), object())


class _BVertex(StateVertex):
    async def run(self, state: object, ctx: Context) -> tuple[Any, Any]:
        return (object(), object())


class _CVertex(StateVertex):
    async def run(self, state: object, ctx: Context) -> tuple[Any, Any]:
        return (object(), object())


class _RequiredParamVertex(StateVertex):
    """Vertex whose constructor requires a positional argument — cannot be auto-instantiated."""

    def __init__(self, required: str) -> None:
        self._required = required

    async def run(self, state: object, ctx: Context) -> tuple[Any, Any]:
        return (object(), object())


class _Sig(enum.Enum):
    ok = "ok"
    fail = "fail"


# ---------------------------------------------------------------------------
# Tests — original (updated where signatures changed)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_transition_stores_from_signal_to() -> None:
    """Transition stores from_node, signal, and to_target exactly as passed."""
    a = _AVertex()
    b = _BVertex()
    t = Transition(from_node=a, signal=_Sig.ok, to_target=b)

    assert t.from_node is a
    assert t.signal is _Sig.ok
    assert t.to_target is b


@pytest.mark.unit
def test_parallel_expand_returns_vertices_list() -> None:
    """Parallel.expand(resolver) returns a list containing all provided vertex instances."""
    a = _AVertex()
    b = _BVertex()
    p = Parallel(a, b)
    resolver = VertexResolver()

    result = p.expand(resolver)

    assert result == [a, b]
    assert result[0] is a
    assert result[1] is b


@pytest.mark.unit
def test_state_graph_get_targets_returns_matching_transition_target() -> None:
    """get_targets(node, signal) returns [b] when a single transition matches."""
    a = _AVertex()
    b = _BVertex()
    graph = StateGraph(start=a, transitions=[Transition(a, _Sig.ok, b)])

    targets = graph.get_targets(a, _Sig.ok)

    assert targets == [b]


@pytest.mark.unit
def test_state_graph_get_targets_no_match_returns_empty() -> None:
    """get_targets returns [] when no transition matches the given node+signal."""
    a = _AVertex()
    b = _BVertex()
    graph = StateGraph(start=a, transitions=[Transition(a, _Sig.ok, b)])

    assert graph.get_targets(a, _Sig.fail) == []
    assert graph.get_targets(b, _Sig.ok) == []


@pytest.mark.unit
def test_state_graph_expand_target_parallel_returns_flat_list() -> None:
    """expand_target(Parallel(a, b)) returns [a, b]."""
    a = _AVertex()
    b = _BVertex()
    graph = StateGraph(start=a, transitions=[])

    result = graph.expand_target(Parallel(a, b))

    assert result == [a, b]


@pytest.mark.unit
def test_state_graph_expand_target_single_vertex_returns_singleton_list() -> None:
    """expand_target(single_vertex) returns [single_vertex]."""
    a = _AVertex()
    b = _BVertex()
    graph = StateGraph(start=a, transitions=[])

    result = graph.expand_target(b)

    assert result == [b]
    assert result[0] is b


@pytest.mark.unit
def test_state_graph_accepts_class_in_transition_auto_resolves() -> None:
    """StateGraph accepts a bare class in transitions and auto-resolves it to an instance."""
    # Must not raise — E020 auto-instantiation is now supported.
    # Both start and from_node use the same class so they share one singleton.
    graph = StateGraph(
        start=_AVertex,
        transitions=[Transition(from_node=_AVertex, signal=_Sig.ok, to_target=_BVertex)],
    )

    targets = graph.get_targets(graph.resolve_start(), _Sig.ok)
    assert len(targets) == 1
    assert isinstance(targets[0], _BVertex)


# ---------------------------------------------------------------------------
# New tests — E020 auto-instantiation
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_transition_holds_class_without_error() -> None:
    """Transition accepts bare classes as from_node and to_target without raising."""
    t = Transition(from_node=_AVertex, signal=_Sig.ok, to_target=_BVertex)

    assert t.from_node is _AVertex
    assert t.to_target is _BVertex


@pytest.mark.unit
def test_parallel_expand_with_resolver() -> None:
    """Parallel(A, B).expand(resolver) returns two resolved instances of the expected types."""
    resolver = VertexResolver()
    p = Parallel(_AVertex, _BVertex)

    result = p.expand(resolver)

    assert len(result) == 2
    assert isinstance(result[0], _AVertex)
    assert isinstance(result[1], _BVertex)


@pytest.mark.unit
def test_state_graph_class_based_topology_resolves_start() -> None:
    """StateGraph(start=MyVertex) auto-instantiates and returns the instance from resolve_start()."""
    graph = StateGraph(
        start=_AVertex,
        transitions=[Transition(_AVertex, _Sig.ok, _BVertex)],
    )

    start = graph.resolve_start()

    assert isinstance(start, _AVertex)


@pytest.mark.unit
def test_state_graph_singleton_identity() -> None:
    """Two transitions pointing to the same class share one singleton instance."""
    graph = StateGraph(
        start=_AVertex,
        transitions=[
            Transition(_AVertex, _Sig.ok, _BVertex),
            Transition(_CVertex, _Sig.ok, _BVertex),
        ],
    )

    start = graph.resolve_start()
    # _AVertex is the start — get_targets routes to _BVertex
    b_from_a = graph.get_targets(start, _Sig.ok)

    # Resolve _CVertex to find its singleton, then get its target
    c_instance = graph._resolver.resolve(_CVertex)  # noqa: SLF001
    b_from_c = graph.get_targets(c_instance, _Sig.ok)

    assert len(b_from_a) == 1
    assert len(b_from_c) == 1
    # Both transitions point to the same _BVertex singleton
    assert b_from_a[0] is b_from_c[0]


@pytest.mark.unit
def test_state_graph_class_without_default_raises_value_error() -> None:
    """StateGraph raises ValueError when a class with required params is used."""
    with pytest.raises(ValueError, match="_RequiredParamVertex"):
        StateGraph(
            start=_RequiredParamVertex,  # type: ignore[arg-type]
            transitions=[],
        )


@pytest.mark.unit
def test_state_graph_mixed_class_and_instance() -> None:
    """Mixed topology of classes and pre-instantiated instances works correctly."""
    b_instance = _BVertex()

    graph = StateGraph(
        start=_AVertex,
        transitions=[Transition(_AVertex, _Sig.ok, b_instance)],
    )

    start = graph.resolve_start()
    assert isinstance(start, _AVertex)

    targets = graph.get_targets(start, _Sig.ok)
    assert len(targets) == 1
    # The pre-instantiated instance is returned unchanged (identity preserved)
    assert targets[0] is b_instance
