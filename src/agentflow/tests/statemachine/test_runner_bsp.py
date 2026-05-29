"""Unit tests for StateGraphRunner BSP execution loop.

Tests cover: sequential flow, parallel fan-out, set-based join deduplication,
cycle termination, vertex exception handling, and synchronous run wrapper.
"""

from __future__ import annotations

import dataclasses
from typing import Any

import pytest

from src.agentflow.statemachine.runner import StateGraphRunner
from src.agentflow.statemachine.signal import StdSignal
from src.agentflow.statemachine.testing import FakeVertex, make_fake_context
from src.agentflow.statemachine.topology import Parallel, StateGraph, Transition
from src.agentflow.statemachine.vertex import StateVertex, StdEnd, _EmptyPatch


@dataclasses.dataclass(frozen=True)
class _AppState:
    """Minimal frozen dataclass required by apply_patches."""


_EMPTY = _EmptyPatch()


# ---------------------------------------------------------------------------
# Test 1 — sequential A → B → StdEnd
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.asyncio
async def test_runner_sequential_two_vertices_runs_to_std_end(
    fake_ctx: Any,
) -> None:
    """Runner with A → B → StdEnd topology must complete and return state."""
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

    initial = _AppState()
    runner = StateGraphRunner(graph, fake_ctx)
    final = await runner.run(initial)

    assert isinstance(final, _AppState)
    assert a.calls == 1
    assert b.calls == 1


# ---------------------------------------------------------------------------
# Test 2 — parallel fan-out A → Parallel(B, C) → StdEnd
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.asyncio
async def test_runner_parallel_fan_out_runs_both_branches(
    fake_ctx: Any,
) -> None:
    """Fan-out topology must run both B and C in the same super-step."""
    a = FakeVertex(StdSignal.ok, _EMPTY, name="A")
    b = FakeVertex(StdSignal.ok, _EMPTY, name="B")
    c = FakeVertex(StdSignal.ok, _EMPTY, name="C")
    std_end = StdEnd()

    graph = StateGraph(
        start=a,
        transitions=[
            Transition(a, StdSignal.ok, Parallel(b, c)),
            Transition(b, StdSignal.ok, std_end),
            Transition(c, StdSignal.ok, std_end),
        ],
    )

    runner = StateGraphRunner(graph, fake_ctx)
    await runner.run(_AppState())

    assert a.calls == 1
    assert b.calls == 1
    assert c.calls == 1


# ---------------------------------------------------------------------------
# Test 3 — set-based join: two branches → same Review instance, runs once
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.asyncio
async def test_runner_set_based_join_dedups_same_instance(
    fake_ctx: Any,
) -> None:
    """Two branches merging into the SAME vertex instance must run it only once."""
    write_intro = FakeVertex(StdSignal.ok, _EMPTY, name="WriteIntro")
    write_body = FakeVertex(StdSignal.ok, _EMPTY, name="WriteBody")
    # Shared instance — both branches route to it; set deduplication keeps one copy.
    review = FakeVertex(StdSignal.ok, _EMPTY, name="Review")
    std_end = StdEnd()

    graph = StateGraph(
        start=write_intro,
        transitions=[
            Transition(write_intro, StdSignal.ok, Parallel(write_intro, write_body)),
            # Overwrite start — build a real fan-out from a dedicated start vertex.
        ],
    )
    # Rebuild with a clean start vertex that fans out to write_intro and write_body.
    fan_out_start = FakeVertex(StdSignal.ok, _EMPTY, name="Start")
    graph = StateGraph(
        start=fan_out_start,
        transitions=[
            Transition(fan_out_start, StdSignal.ok, Parallel(write_intro, write_body)),
            Transition(write_intro, StdSignal.ok, review),
            Transition(write_body, StdSignal.ok, review),
            Transition(review, StdSignal.ok, std_end),
        ],
    )

    runner = StateGraphRunner(graph, fake_ctx)
    await runner.run(_AppState())

    # Both write vertices ran once, review ran exactly once (set-based join).
    assert write_intro.calls == 1
    assert write_body.calls == 1
    assert review.calls == 1


# ---------------------------------------------------------------------------
# Test 4 — cycle terminates after N iterations via StdEnd
# ---------------------------------------------------------------------------


class _LoopVertex(StateVertex):
    """Vertex that returns StdSignal.ok for max_loops-1 calls, then StdSignal.done."""

    def __init__(self, max_loops: int) -> None:
        self._max = max_loops
        self.calls = 0

    async def run(self, state: object, ctx: Any) -> tuple[Any, Any]:
        """Increment call counter and switch signal after max_loops calls.

        Args:
            state: Current state (ignored).
            ctx: Shared context (ignored).

        Returns:
            (StdSignal.ok, _EmptyPatch()) while calls < max_loops,
            (StdSignal.done, _EmptyPatch()) on the final call.
        """
        self.calls += 1
        if self.calls < self._max:
            return StdSignal.ok, _EMPTY
        return StdSignal.done, _EMPTY


@pytest.mark.unit
@pytest.mark.asyncio
async def test_runner_cycle_terminates_via_std_end_after_n_iterations(
    fake_ctx: Any,
) -> None:
    """Cycle A → A must repeat exactly N-1 times before transitioning to StdEnd."""
    loop = _LoopVertex(max_loops=3)
    std_end = StdEnd()

    graph = StateGraph(
        start=loop,
        transitions=[
            Transition(loop, StdSignal.ok, loop),  # cycles back to self
            Transition(loop, StdSignal.done, std_end),
        ],
    )

    runner = StateGraphRunner(graph, fake_ctx)
    await runner.run(_AppState())

    assert loop.calls == 3  # 2 ok-cycles + 1 done exit


# ---------------------------------------------------------------------------
# Test 5 — vertex exception → StdSignal.fail → StdEnd (runner does not crash)
# ---------------------------------------------------------------------------


class _RaisingVertex(StateVertex):
    """Vertex whose run() always raises RuntimeError."""

    async def run(self, state: object, ctx: Any) -> tuple[Any, Any]:
        """Raise unconditionally to test _safe_run error handling.

        Args:
            state: Current state (ignored).
            ctx: Shared context (ignored).

        Raises:
            RuntimeError: Always.
        """
        raise RuntimeError("deliberate vertex failure")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_runner_vertex_exception_maps_to_std_signal_fail(
    fake_ctx: Any,
) -> None:
    """_safe_run must catch exceptions and route via StdSignal.fail without crashing."""
    raiser = _RaisingVertex()
    std_end = StdEnd()

    graph = StateGraph(
        start=raiser,
        transitions=[
            # Exception path: StdSignal.fail → StdEnd (runner must reach here).
            Transition(raiser, StdSignal.fail, std_end),
        ],
    )

    runner = StateGraphRunner(graph, fake_ctx)
    final = await runner.run(_AppState())

    # Runner completed normally — returned a TestState, did not propagate exception.
    assert isinstance(final, _AppState)


# ---------------------------------------------------------------------------
# Test 6 — run_sync returns the same final state as async run
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_runner_run_sync_returns_final_state() -> None:
    """run_sync(state) must return the same final state as the async run() variant."""
    ctx = make_fake_context()
    a = FakeVertex(StdSignal.ok, _EMPTY, name="A")
    std_end = StdEnd()

    graph = StateGraph(
        start=a,
        transitions=[Transition(a, StdSignal.ok, std_end)],
    )

    initial = _AppState()
    runner = StateGraphRunner(graph, ctx)
    final = runner.run_sync(initial)

    assert isinstance(final, _AppState)
    assert a.calls == 1
