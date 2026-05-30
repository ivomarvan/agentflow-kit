"""Unit tests for LiveGraphHooks and GraphRenderer active-node coloring."""

from __future__ import annotations

import enum
from dataclasses import dataclass
from typing import Any

import pytest

from agentflow.describable.graph import Graph, Vertex
from agentflow.describable.graph_renderer import GraphRenderer
from agentflow.statemachine.context import Context
from agentflow.statemachine.hooks import LiveGraphHooks
from agentflow.statemachine.runner import StateGraphRunner
from agentflow.statemachine.testing.fakes import make_fake_context
from agentflow.statemachine.topology import StateGraph, Transition
from agentflow.statemachine.vertex import StateVertex, StdEnd


@dataclass(frozen=True)
class _EmptyState:
    """Minimal frozen dataclass used as state in hook tests."""


class _Sig(enum.Enum):
    ok = "ok"


class NodeA(StateVertex):
    async def run(self, state: object, ctx: Context) -> tuple[Any, Any]:
        return _Sig.ok, None


class NodeB(StateVertex):
    async def run(self, state: object, ctx: Context) -> tuple[Any, Any]:
        return _Sig.ok, None


def _build_linear_graph() -> StateGraph:
    """Build a 2-vertex linear graph: NodeA → NodeB → StdEnd."""
    return StateGraph(
        start=NodeA,
        transitions=[
            Transition(NodeA, _Sig.ok, NodeB),
            Transition(NodeB, _Sig.ok, StdEnd),
        ],
    )


@pytest.mark.unit
def test_live_graph_hooks_records_one_snapshot_per_super_step() -> None:
    """Each completed super-step must add exactly one entry to snapshots."""
    hooks = LiveGraphHooks()
    graph = _build_linear_graph()
    ctx = make_fake_context()
    runner = StateGraphRunner(graph=graph, context=ctx, hooks=hooks)
    runner.run_sync(_EmptyState())

    # NodeA runs (step 1), NodeB runs (step 2), StdEnd terminates — 2 snapshots.
    assert len(hooks.snapshots) == 2


@pytest.mark.unit
def test_live_graph_hooks_snapshot_contains_active_node_names() -> None:
    """The first snapshot must report NodeA as the only active vertex name."""
    hooks = LiveGraphHooks()
    graph = _build_linear_graph()
    ctx = make_fake_context()
    runner = StateGraphRunner(graph=graph, context=ctx, hooks=hooks)
    runner.run_sync(_EmptyState())

    step_number, active_names = hooks.snapshots[0]
    assert step_number == 1
    assert active_names == {NodeA.__name__}


@pytest.mark.unit
def test_graph_renderer_colors_active_node_in_dot_output() -> None:
    """GraphRenderer.to_dot() must include #90EE90 fillcolor for active vertices."""
    root = Vertex(id="root", label="root", description={})
    active_v = Vertex(id="A", label="A", description={}, attributes={"active": True})
    root.children = [active_v]
    graph = Graph(root=root)

    dot = GraphRenderer.to_dot(graph)

    assert "90EE90" in dot
