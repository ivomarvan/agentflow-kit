"""Tests for the declarative AgentApp constructor (T103-07)."""
from __future__ import annotations

import dataclasses
from typing import Any

import pytest

from agentflow import AgentApp
from agentflow.statemachine import (
    Context,
    RunStats,
    StateGraph,
    StateVertex,
    StdEnd,
    StdSignal,
    Transition,
)
from agentflow.statemachine.testing.fakes import make_fake_context
from agentflow.statemachine.vertex import _EmptyPatch

# ---------------------------------------------------------------------------
# Minimal helpers — a trivial one-step graph
# ---------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class _SimpleState:
    final_answer: str = "ok"


@dataclasses.dataclass
class _SimplePatch:
    final_answer: str | None = None


class _SimpleEndVertex(StateVertex):
    """Returns StdSignal.done immediately; carries no application logic."""

    async def run(self, state: object, ctx: Context) -> tuple[Any, Any]:
        return StdSignal.done, _EmptyPatch()


def _make_trivial_graph() -> StateGraph:
    """Return a StateGraph that terminates after one vertex."""
    vertex = _SimpleEndVertex()
    end = StdEnd()
    return StateGraph(
        start=vertex,
        transitions=[Transition(vertex, StdSignal.done, end)],
    )


def _make_trivial_context() -> Context:
    return make_fake_context()


# ---------------------------------------------------------------------------
# Tests — declarative construction
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestAgentAppDeclarativeConstruction:
    def test_constructs_with_context_and_state_graph(self) -> None:
        """AgentApp(context=ctx, state_graph=graph) must construct without subclassing."""
        ctx = _make_trivial_context()
        graph = _make_trivial_graph()
        app = AgentApp(context=ctx, state_graph=graph)
        assert app is not None

    def test_sample_prompts_returns_provided_list(self) -> None:
        """sample_prompts property must return the list passed to the constructor."""
        ctx = _make_trivial_context()
        graph = _make_trivial_graph()
        prompts = ["hello", "world"]
        app = AgentApp(context=ctx, state_graph=graph, sample_prompts=prompts)
        assert app.sample_prompts == prompts

    def test_sample_prompts_empty_by_default(self) -> None:
        """sample_prompts must return [] when not provided."""
        app = AgentApp()
        assert app.sample_prompts == []


# ---------------------------------------------------------------------------
# Tests — run_and_stats
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestAgentAppRunAndStats:
    def test_run_and_stats_returns_tuple(self) -> None:
        """run_and_stats() must return a two-tuple (result, RunStats)."""
        ctx = _make_trivial_context()
        graph = _make_trivial_graph()
        app = AgentApp(
            context=ctx,
            state_graph=graph,
            initial_state_factory=lambda q: _SimpleState(),
        )
        result, stats = app.run_and_stats("hello")
        assert isinstance(stats, RunStats)

    def test_run_and_stats_wall_time_is_positive(self) -> None:
        """stats.wall_time_ms must be > 0 after a completed run."""
        ctx = _make_trivial_context()
        graph = _make_trivial_graph()
        app = AgentApp(
            context=ctx,
            state_graph=graph,
            initial_state_factory=lambda q: _SimpleState(),
        )
        _result, stats = app.run_and_stats("hello")
        assert stats.wall_time_ms > 0

    def test_run_and_stats_result_is_str_or_none(self) -> None:
        """The first element of the tuple must be a str or None."""
        ctx = _make_trivial_context()
        graph = _make_trivial_graph()
        app = AgentApp(
            context=ctx,
            state_graph=graph,
            initial_state_factory=lambda q: _SimpleState(),
        )
        result, _stats = app.run_and_stats("hello")
        assert result is None or isinstance(result, str)

    def test_run_and_stats_extracts_final_answer(self) -> None:
        """When the final state has a non-empty final_answer, it is returned."""
        ctx = _make_trivial_context()
        graph = _make_trivial_graph()
        app = AgentApp(
            context=ctx,
            state_graph=graph,
            initial_state_factory=lambda q: _SimpleState(final_answer="ok"),
        )
        result, _stats = app.run_and_stats("question")
        assert result == "ok"


# ---------------------------------------------------------------------------
# Tests — initial_state_factory
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestAgentAppInitialStateFactory:
    def test_initial_state_factory_is_called_with_prompt(self) -> None:
        """initial_state_factory receives the question string."""
        received: list[str] = []

        def factory(q: str) -> _SimpleState:
            received.append(q)
            return _SimpleState()

        ctx = _make_trivial_context()
        graph = _make_trivial_graph()
        app = AgentApp(context=ctx, state_graph=graph, initial_state_factory=factory)
        app.run_and_stats("test-prompt")
        assert received == ["test-prompt"]


# ---------------------------------------------------------------------------
# Tests — subclassing still works
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestAgentAppSubclassing:
    def test_subclass_override_run_workflow(self) -> None:
        """Subclass may override run_workflow() and run_and_stats uses it."""

        class MyApp(AgentApp):
            async def run_workflow(self) -> str | None:
                return "subclass-result"

        app = MyApp()
        result, stats = app.run_and_stats("anything")
        assert result == "subclass-result"
        assert isinstance(stats, RunStats)

    def test_subclass_sample_prompts_not_required(self) -> None:
        """Subclass without sample_prompts override returns empty list."""

        class MyApp(AgentApp):
            async def run_workflow(self) -> str | None:
                return None

        app = MyApp()
        assert app.sample_prompts == []

    def test_run_workflow_raises_without_context_or_override(self) -> None:
        """Base AgentApp.run_workflow() raises NotImplementedError when no context given."""
        import asyncio

        app = AgentApp()
        with pytest.raises(NotImplementedError):
            asyncio.run(app.run_workflow())
