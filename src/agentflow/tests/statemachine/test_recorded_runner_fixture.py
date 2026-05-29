"""Integration tests for the recorded_runner fixture.

Verifies that RecorderHooks.history is populated correctly after a full
BSP runner execution using a deterministic 3-node graph: A → B → StdEnd.

End nodes (StdEnd) run outside the super-step counter and are NOT captured
as records — a 3-node A → B → StdEnd graph produces exactly 2 history entries.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Callable
from typing import Annotated

import pytest

from src.agentflow.statemachine.hooks import RecorderHooks
from src.agentflow.statemachine.runner import StateGraphRunner
from src.agentflow.statemachine.signal import StdSignal
from src.agentflow.statemachine.testing import FakeVertex
from src.agentflow.statemachine.topology import StateGraph, Transition
from src.agentflow.statemachine.vertex import StdEnd, _EmptyPatch


@dataclasses.dataclass(frozen=True)
class _CountState:
    """Minimal frozen state with an additive reducer on the count field."""

    count: Annotated[int, lambda a, b: a + b] = 0


@dataclasses.dataclass(frozen=True)
class _CountPatch:
    """Patch that contributes an integer increment to _CountState.count."""

    count: int | None = None


_EMPTY = _EmptyPatch()


def _make_linear_graph() -> tuple[FakeVertex, FakeVertex, StateGraph]:
    """Build a deterministic A → B → StdEnd graph using FakeVertex.

    Returns:
        Tuple of (vertex_a, vertex_b, graph) — vertices are exposed so tests
        can assert on identity in history.active_nodes.
    """
    a = FakeVertex(StdSignal.ok, _EMPTY, name="A")
    b = FakeVertex(StdSignal.ok, _EMPTY, name="B")
    std_end = StdEnd()
    graph = StateGraph(
        start=a,
        transitions=[
            Transition(a, StdSignal.ok, b),
            Transition(b, StdSignal.ok, std_end),
        ],
    )
    return a, b, graph


# ---------------------------------------------------------------------------
# Test 1 — history length
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_recorded_runner_history_has_correct_length(
    recorded_runner: Callable[[StateGraph], tuple[StateGraphRunner, RecorderHooks]],
) -> None:
    """len(recorder.history) == 2: one record per non-End super-step."""
    _, _, graph = _make_linear_graph()
    runner, recorder = recorded_runner(graph)

    runner.run_sync(_CountState())

    assert len(recorder.history) == 2


# ---------------------------------------------------------------------------
# Test 2 — active node identity per super-step
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_recorded_runner_active_nodes_sequence(
    recorded_runner: Callable[[StateGraph], tuple[StateGraphRunner, RecorderHooks]],
) -> None:
    """history[0] captures vertex A; history[1] captures vertex B."""
    a, b, graph = _make_linear_graph()
    runner, recorder = recorded_runner(graph)

    runner.run_sync(_CountState())

    assert recorder.history[0].active_nodes == [a]
    assert recorder.history[1].active_nodes == [b]


# ---------------------------------------------------------------------------
# Test 3 — state evolution across super-steps
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_recorded_runner_state_evolves_across_steps(
    recorded_runner: Callable[[StateGraph], tuple[StateGraphRunner, RecorderHooks]],
) -> None:
    """state_after.count grows by 1 each step via the additive reducer."""
    a = FakeVertex(StdSignal.ok, _CountPatch(count=1), name="A")
    b = FakeVertex(StdSignal.ok, _CountPatch(count=1), name="B")
    std_end = StdEnd()
    graph = StateGraph(
        start=a,
        transitions=[
            Transition(a, StdSignal.ok, b),
            Transition(b, StdSignal.ok, std_end),
        ],
    )
    runner, recorder = recorded_runner(graph)
    runner.run_sync(_CountState())

    state_after_step1 = recorder.history[0].state_after
    state_after_step2 = recorder.history[1].state_after

    assert isinstance(state_after_step1, _CountState)
    assert isinstance(state_after_step2, _CountState)
    # After step 1: reducer(0, 1) = 1
    assert state_after_step1.count == 1
    # After step 2: reducer(1, 1) = 2
    assert state_after_step2.count == 2
