"""Unit tests for StateGraphRunner.run_until() and resume() with checkpointing.

Covers: pause-on-predicate, checkpoint persistence per step, resume from checkpoint,
full-run without pause, and JsonFileCheckpointStore JSON roundtrip.
"""

from __future__ import annotations

import dataclasses
from typing import Any

import pytest

from src.agentflow.statemachine.checkpoint import (
    CheckpointRecord,
    InMemoryCheckpointStore,
    JsonFileCheckpointStore,
)
from src.agentflow.statemachine.context import Context
from src.agentflow.statemachine.runner import StateGraphRunner
from src.agentflow.statemachine.signal import StdSignal
from src.agentflow.statemachine.testing import make_fake_context
from src.agentflow.statemachine.topology import StateGraph, Transition
from src.agentflow.statemachine.vertex import StateVertex, StdEnd


# ---------------------------------------------------------------------------
# Shared test fixtures
# ---------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class SimpleState:
    """Minimal state with a single integer field for increment tracking."""

    value: int = 0


@dataclasses.dataclass(frozen=True)
class _SimpleStatePatch:
    """Patch for SimpleState — None means 'do not overwrite'."""

    value: int | None = None


class _VertexA(StateVertex):
    """First node in the A → B → StdEnd test graph; increments value by 1."""

    async def run(self, state: Any, ctx: Context) -> tuple[Any, Any]:
        """Increment state.value by 1 and signal ok.

        Args:
            state: Current SimpleState.
            ctx: Shared context (unused).

        Returns:
            Tuple of (StdSignal.ok, patch with value = state.value + 1).
        """
        return StdSignal.ok, _SimpleStatePatch(value=state.value + 1)


class _VertexB(StateVertex):
    """Second node in the A → B → StdEnd test graph; increments value by 1."""

    async def run(self, state: Any, ctx: Context) -> tuple[Any, Any]:
        """Increment state.value by 1 and signal ok.

        Args:
            state: Current SimpleState.
            ctx: Shared context (unused).

        Returns:
            Tuple of (StdSignal.ok, patch with value = state.value + 1).
        """
        return StdSignal.ok, _SimpleStatePatch(value=state.value + 1)


def _make_linear_graph() -> StateGraph:
    """Build linear A → B → StdEnd graph with singleton vertices."""
    a = _VertexA()
    b = _VertexB()
    end = StdEnd()
    return StateGraph(
        start=a,
        transitions=[
            Transition(a, StdSignal.ok, b),
            Transition(b, StdSignal.ok, end),
        ],
    )


# ---------------------------------------------------------------------------
# Test 1 — run_until stops when predicate is true at step 1
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.asyncio
async def test_run_until_stops_when_predicate_true_at_step_1(
    fake_ctx: Any,
) -> None:
    """run_until with predicate step>=1 must pause after A runs, before B runs.

    After step 1 (A executed), predicate(1, ...) returns True and the runner
    returns. Value must be 1 (only A incremented it).
    """
    graph = _make_linear_graph()
    store = InMemoryCheckpointStore()
    runner = StateGraphRunner(graph, fake_ctx)

    final_state = await runner.run_until(
        SimpleState(value=0),
        predicate=lambda step, _state, _nodes: step >= 1,
        store=store,
        run_id="run-1",
    )

    assert isinstance(final_state, SimpleState)
    assert final_state.value == 1, "Only A should have run (value incremented once)"


# ---------------------------------------------------------------------------
# Test 2 — run_until saves checkpoint after stopping at step 1
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.asyncio
async def test_run_until_saves_checkpoint_per_step(
    fake_ctx: Any,
) -> None:
    """After run_until pauses at step 1, the store must contain a checkpoint for step 1.

    The checkpoint must record the state after A ran (value==1) and must have
    active_node_names pointing to the next vertex (B).
    """
    graph = _make_linear_graph()
    store = InMemoryCheckpointStore()
    runner = StateGraphRunner(graph, fake_ctx)

    await runner.run_until(
        SimpleState(value=0),
        predicate=lambda step, _state, _nodes: step >= 1,
        store=store,
        run_id="run-2",
    )

    steps = await store.list_steps("run-2")
    assert steps == [1], f"Expected [1], got {steps}"

    record = await store.load("run-2", 1)
    assert isinstance(record.state, SimpleState)
    assert record.state.value == 1
    assert record.active_node_names == ["_VertexB"]


# ---------------------------------------------------------------------------
# Test 3 — resume continues from checkpoint to completion
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.asyncio
async def test_resume_continues_to_completion(
    fake_ctx: Any,
) -> None:
    """Pause after step 1, resume — B must run and final value must be 2."""
    graph = _make_linear_graph()
    store = InMemoryCheckpointStore()
    runner = StateGraphRunner(graph, fake_ctx)

    await runner.run_until(
        SimpleState(value=0),
        predicate=lambda step, _state, _nodes: step >= 1,
        store=store,
        run_id="run-3",
    )

    final_state = await runner.resume(store, "run-3", from_step=1)

    assert isinstance(final_state, SimpleState)
    assert final_state.value == 2, "B must have run, incrementing value to 2"


# ---------------------------------------------------------------------------
# Test 4 — run_until completes normally when predicate never returns True
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.asyncio
async def test_run_until_completes_normally_when_predicate_never_true(
    fake_ctx: Any,
) -> None:
    """When predicate always returns False, run_until runs fully and saves all checkpoints.

    Linear A → B → StdEnd produces 2 non-End super-steps, so 2 checkpoints
    must be saved (steps 1 and 2).
    """
    graph = _make_linear_graph()
    store = InMemoryCheckpointStore()
    runner = StateGraphRunner(graph, fake_ctx)

    final_state = await runner.run_until(
        SimpleState(value=0),
        predicate=lambda _step, _state, _nodes: False,
        store=store,
        run_id="run-4",
    )

    assert isinstance(final_state, SimpleState)
    assert final_state.value == 2, "Both A and B must have run"

    steps = await store.list_steps("run-4")
    assert steps == [1, 2], f"Expected [1, 2], got {steps}"


# ---------------------------------------------------------------------------
# Test 5 — JsonFileCheckpointStore save/load roundtrip
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.asyncio
async def test_json_file_store_save_load_roundtrip(tmp_path: Any) -> None:
    """Save a CheckpointRecord to disk and reload it; all fields must be equal.

    Uses tmp_path pytest fixture so no permanent files are created.
    The state_factory reconstructs SimpleState from the raw dict.
    """

    def _factory(qualname: str, data: dict[str, Any]) -> Any:
        return SimpleState(**data)

    store = JsonFileCheckpointStore(base_dir=tmp_path / "checkpoints", state_factory=_factory)
    state = SimpleState(value=99)
    original = CheckpointRecord(
        run_id="test-run",
        step=3,
        state=state,
        active_node_names=["_VertexA", "_VertexB"],
    )

    await store.save(original)

    expected_path = tmp_path / "checkpoints" / "test-run" / "0003.json"
    assert expected_path.exists(), f"Expected JSON file at {expected_path}"

    loaded = await store.load("test-run", 3)

    assert loaded.run_id == original.run_id
    assert loaded.step == original.step
    assert isinstance(loaded.state, SimpleState)
    assert loaded.state.value == 99
    assert loaded.active_node_names == original.active_node_names

    steps = await store.list_steps("test-run")
    assert steps == [3]
