"""Tests for StateGraph.initialized_vertexes feature (T103-03)."""
from __future__ import annotations

from enum import auto
from typing import Any

import pytest

from agentflow.statemachine import Signal, StateVertex
from agentflow.statemachine.context import Context
from agentflow.statemachine.topology import StateGraph, Transition
from agentflow.statemachine.vertex import StdEnd

# ---------------------------------------------------------------------------
# Minimal helpers
# ---------------------------------------------------------------------------


class _Sig(Signal):
    done = auto()


class _PlainVertex(StateVertex):
    """Vertex with no required parameters — can be auto-instantiated."""

    async def run(self, state: object, ctx: Context) -> tuple[Any, Any]:
        return _Sig.done, object()


class _ParamVertex(StateVertex):
    """Vertex with a configurable parameter."""

    param: int = 0

    async def run(self, state: object, ctx: Context) -> tuple[Any, Any]:
        return _Sig.done, object()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestInitializedVertexes:
    def test_pre_instantiated_vertex_is_reused(self) -> None:
        """When an instance is in initialized_vertexes it must be reused, not cloned."""
        v_instance = _PlainVertex()
        end = StdEnd()
        graph = StateGraph(
            start=_PlainVertex,
            transitions=[Transition(_PlainVertex, _Sig.done, StdEnd)],
            initialized_vertexes=[v_instance, end],
        )
        resolved_start = graph.resolve_start()
        assert resolved_start is v_instance, (
            "resolve_start() must return the pre-seeded instance, not a new one"
        )

    def test_class_resolves_to_seeded_instance_in_transitions(self) -> None:
        """Class references in transitions must resolve to the seeded instance."""
        v_instance = _PlainVertex()
        end = StdEnd()
        graph = StateGraph(
            start=_PlainVertex,
            transitions=[Transition(_PlainVertex, _Sig.done, StdEnd)],
            initialized_vertexes=[v_instance, end],
        )
        targets = graph.get_targets(graph.resolve_start(), _Sig.done)
        assert len(targets) == 1
        assert targets[0] is end

    def test_class_without_seed_is_auto_instantiated(self) -> None:
        """A class absent from initialized_vertexes falls back to auto-instantiation."""
        graph = StateGraph(
            start=_PlainVertex,
            transitions=[Transition(_PlainVertex, _Sig.done, StdEnd)],
            initialized_vertexes=None,
        )
        resolved = graph.resolve_start()
        assert isinstance(resolved, _PlainVertex)

    def test_seeded_instance_preserves_custom_param(self) -> None:
        """An instance seeded with param=3 must still have param=3 after resolution."""
        v_custom = _ParamVertex(param=3)
        end = StdEnd()
        graph = StateGraph(
            start=_ParamVertex,
            transitions=[Transition(_ParamVertex, _Sig.done, StdEnd)],
            initialized_vertexes=[v_custom, end],
        )
        resolved = graph.resolve_start()
        assert resolved is v_custom
        assert resolved.param == 3  # type: ignore[union-attr]

    def test_empty_initialized_vertexes_list_behaves_like_none(self) -> None:
        """An empty list for initialized_vertexes must not break construction."""
        graph = StateGraph(
            start=_PlainVertex,
            transitions=[Transition(_PlainVertex, _Sig.done, StdEnd)],
            initialized_vertexes=[],
        )
        assert isinstance(graph.resolve_start(), _PlainVertex)
