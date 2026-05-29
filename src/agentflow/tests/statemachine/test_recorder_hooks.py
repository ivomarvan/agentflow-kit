"""Unit tests for RecorderHooks and SuperStepRecord.

All tests use a deterministic 3-step linear graph (A → B → C → StdEnd)
to verify that RecorderHooks captures the correct data at each phase.
"""

from __future__ import annotations

import dataclasses

import pytest

from src.agentflow.statemachine.hooks import RecorderHooks
from src.agentflow.statemachine.runner import StateGraphRunner
from src.agentflow.statemachine.signal import StdSignal
from src.agentflow.statemachine.testing import FakeVertex, make_fake_context
from src.agentflow.statemachine.topology import StateGraph, Transition
from src.agentflow.statemachine.vertex import StdEnd, _EmptyPatch


@dataclasses.dataclass(frozen=True)
class _State:
    """Minimal frozen state for RecorderHooks tests."""

    counter: int = 0


@dataclasses.dataclass(frozen=True)
class _Patch:
    """Patch that can update the counter field."""

    counter: int | None = None


_EMPTY = _EmptyPatch()


def _make_linear_graph(
    a: FakeVertex,
    b: FakeVertex,
    c: FakeVertex,
) -> StateGraph:
    """Build A → B → C → StdEnd linear graph for tests.

    Args:
        a: Start vertex.
        b: Second vertex.
        c: Third vertex.

    Returns:
        StateGraph with 3 linear hops to StdEnd.
    """
    std_end = StdEnd()
    return StateGraph(
        start=a,
        transitions=[
            Transition(a, StdSignal.ok, b),
            Transition(b, StdSignal.ok, c),
            Transition(c, StdSignal.ok, std_end),
        ],
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_recorder_history_length_matches_super_steps() -> None:
    """3-step linear run must produce exactly 3 records in history."""
    a = FakeVertex(StdSignal.ok, _EMPTY, name="A")
    b = FakeVertex(StdSignal.ok, _EMPTY, name="B")
    c = FakeVertex(StdSignal.ok, _EMPTY, name="C")
    graph = _make_linear_graph(a, b, c)

    recorder = RecorderHooks()
    runner = StateGraphRunner(graph, make_fake_context(), hooks=recorder)
    await runner.run(_State())

    assert len(recorder.history) == 3


@pytest.mark.unit
@pytest.mark.asyncio
async def test_recorder_captures_state_before_and_after() -> None:
    """state_before and state_after must differ when a patch modifies the state."""
    patch_with_change = _Patch(counter=42)
    a = FakeVertex(StdSignal.ok, patch_with_change, name="A")
    b = FakeVertex(StdSignal.ok, _EMPTY, name="B")
    c = FakeVertex(StdSignal.ok, _EMPTY, name="C")
    graph = _make_linear_graph(a, b, c)

    recorder = RecorderHooks()
    runner = StateGraphRunner(graph, make_fake_context(), hooks=recorder)
    await runner.run(_State())

    first = recorder.history[0]
    assert isinstance(first.state_before, _State)
    assert isinstance(first.state_after, _State)
    assert first.state_before != first.state_after
    assert first.state_before.counter == 0
    assert first.state_after.counter == 42


@pytest.mark.unit
@pytest.mark.asyncio
async def test_recorder_captures_active_nodes() -> None:
    """First record's active_nodes must contain vertex A (the start vertex)."""
    a = FakeVertex(StdSignal.ok, _EMPTY, name="A")
    b = FakeVertex(StdSignal.ok, _EMPTY, name="B")
    c = FakeVertex(StdSignal.ok, _EMPTY, name="C")
    graph = _make_linear_graph(a, b, c)

    recorder = RecorderHooks()
    runner = StateGraphRunner(graph, make_fake_context(), hooks=recorder)
    await runner.run(_State())

    assert a in recorder.history[0].active_nodes


@pytest.mark.unit
@pytest.mark.asyncio
async def test_recorder_captures_results_signals() -> None:
    """First record's results must contain (a, StdSignal.ok, patch)."""
    patch = _Patch(counter=1)
    a = FakeVertex(StdSignal.ok, patch, name="A")
    b = FakeVertex(StdSignal.ok, _EMPTY, name="B")
    c = FakeVertex(StdSignal.ok, _EMPTY, name="C")
    graph = _make_linear_graph(a, b, c)

    recorder = RecorderHooks()
    runner = StateGraphRunner(graph, make_fake_context(), hooks=recorder)
    await runner.run(_State())

    results = recorder.history[0].results
    assert len(results) == 1
    vertex, signal, _ = results[0]
    assert vertex is a
    assert signal is StdSignal.ok


@pytest.mark.unit
@pytest.mark.asyncio
async def test_recorder_captures_next_active() -> None:
    """First record's next_active must contain vertex B (successor of A)."""
    a = FakeVertex(StdSignal.ok, _EMPTY, name="A")
    b = FakeVertex(StdSignal.ok, _EMPTY, name="B")
    c = FakeVertex(StdSignal.ok, _EMPTY, name="C")
    graph = _make_linear_graph(a, b, c)

    recorder = RecorderHooks()
    runner = StateGraphRunner(graph, make_fake_context(), hooks=recorder)
    await runner.run(_State())

    assert b in recorder.history[0].next_active
