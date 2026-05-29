"""Unit tests for topology.py — Transition, Parallel, StateGraph."""

from __future__ import annotations

import enum
from typing import Any

import pytest

from src.agentflow.statemachine.context import Context
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


class _Sig(enum.Enum):
    ok = "ok"
    fail = "fail"


# ---------------------------------------------------------------------------
# Tests
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
    """Parallel.expand() returns a list containing all provided vertex instances."""
    a = _AVertex()
    b = _BVertex()
    p = Parallel(a, b)

    result = p.expand()

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
def test_state_graph_rejects_class_in_transitions_with_helpful_error() -> None:
    """StateGraph raises TypeError with 'E020' text when a class is in transitions."""
    a = _AVertex()

    with pytest.raises(TypeError, match="E020"):
        StateGraph(
            start=a,
            transitions=[Transition(from_node=_AVertex, signal=_Sig.ok, to_target=a)],  # type: ignore[arg-type]
        )
