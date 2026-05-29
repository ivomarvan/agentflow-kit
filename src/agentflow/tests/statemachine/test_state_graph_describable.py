"""Unit tests for StateGraph(Describable) — E060 T010.

Verifies that StateGraph is a proper Describable subclass and that
get_graph() produces a correct topology Graph (nodes and edges).
"""

from __future__ import annotations

import enum
from typing import Any

import pytest

from src.agentflow.describable.describable import Describable
from src.agentflow.describable.graph import Graph
from src.agentflow.statemachine.context import Context
from src.agentflow.statemachine.topology import Parallel, StateGraph, Transition
from src.agentflow.statemachine.vertex import StateVertex


class _A(StateVertex):
    async def run(self, state: object, ctx: Context) -> tuple[Any, Any]:
        return (object(), object())


class _B(StateVertex):
    async def run(self, state: object, ctx: Context) -> tuple[Any, Any]:
        return (object(), object())


class _C(StateVertex):
    async def run(self, state: object, ctx: Context) -> tuple[Any, Any]:
        return (object(), object())


class _Sig(enum.Enum):
    go = "go"
    done = "done"
    branch = "branch"


@pytest.mark.unit
def test_state_graph_is_describable_instance() -> None:
    """StateGraph is an instance of Describable after E060 T010."""
    graph = StateGraph(start=_A, transitions=[])
    assert isinstance(graph, Describable)


@pytest.mark.unit
def test_get_graph_root_has_correct_node_count() -> None:
    """get_graph().root.children contains one Vertex per unique topology node."""
    graph = StateGraph(
        start=_A,
        transitions=[
            Transition(_A, _Sig.go, _B),
            Transition(_B, _Sig.done, _C),
        ],
    )
    g = graph.get_graph()

    assert isinstance(g, Graph)
    # 3 unique nodes: _A, _B, _C
    assert len(g.root.children) == 3
    assert g.root.description["nodes"] == 3
    assert g.root.description["transitions"] == 2


@pytest.mark.unit
def test_get_graph_edges_count_matches_transitions() -> None:
    """get_graph().edges has exactly one Edge per non-Parallel transition."""
    graph = StateGraph(
        start=_A,
        transitions=[
            Transition(_A, _Sig.go, _B),
            Transition(_B, _Sig.done, _C),
        ],
    )
    g = graph.get_graph()

    assert len(g.edges) == 2


@pytest.mark.unit
def test_get_graph_edge_labels_are_signal_names() -> None:
    """Edge.label equals the .name attribute of each signal enum member."""
    graph = StateGraph(
        start=_A,
        transitions=[
            Transition(_A, _Sig.go, _B),
            Transition(_B, _Sig.done, _C),
        ],
    )
    g = graph.get_graph()

    labels = {e.label for e in g.edges}
    assert labels == {"go", "done"}
