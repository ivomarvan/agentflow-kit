"""Unit tests for CheckpointRecord, CheckpointStore Protocol, and InMemoryCheckpointStore."""

from __future__ import annotations

import dataclasses

import pytest

from src.agentflow.statemachine.checkpoint import (
    CheckpointRecord,
    CheckpointStore,
    InMemoryCheckpointStore,
)


@dataclasses.dataclass(frozen=True)
class _FakeState:
    value: int = 0


# ---------------------------------------------------------------------------
# Test 1 — roundtrip: save then load returns identical record
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_in_memory_store_save_and_load_roundtrip() -> None:
    store = InMemoryCheckpointStore()
    state = _FakeState(value=42)
    record = CheckpointRecord(
        run_id="run-1",
        step=1,
        state=state,
        active_node_names=["NodeA", "NodeB"],
    )

    await store.save(record)
    loaded = await store.load("run-1", 1)

    assert loaded.run_id == "run-1"
    assert loaded.step == 1
    assert loaded.state is state
    assert loaded.active_node_names == ["NodeA", "NodeB"]


# ---------------------------------------------------------------------------
# Test 2 — load raises KeyError for a step that was never saved
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_in_memory_store_load_raises_keyerror_on_missing() -> None:
    store = InMemoryCheckpointStore()

    with pytest.raises(KeyError):
        await store.load("no-such-run", 99)


# ---------------------------------------------------------------------------
# Test 3 — list_steps returns steps in ascending order regardless of insert order
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_in_memory_store_list_steps_returns_sorted() -> None:
    store = InMemoryCheckpointStore()
    state = _FakeState()

    for step in (3, 1, 2):
        await store.save(CheckpointRecord(run_id="run-x", step=step, state=state, active_node_names=[]))

    steps = await store.list_steps("run-x")

    assert steps == [1, 2, 3]


# ---------------------------------------------------------------------------
# Test 4 — CheckpointRecord dataclass exposes expected fields with correct types
# ---------------------------------------------------------------------------


def test_checkpoint_record_dataclass_fields() -> None:
    fields = {f.name: f.type for f in dataclasses.fields(CheckpointRecord)}

    assert "run_id" in fields
    assert "step" in fields
    assert "state" in fields
    assert "active_node_names" in fields

    record = CheckpointRecord(run_id="r", step=5, state=None, active_node_names=["X"])
    assert isinstance(record.run_id, str)
    assert isinstance(record.step, int)
    assert isinstance(record.active_node_names, list)


# ---------------------------------------------------------------------------
# Test 5 — InMemoryCheckpointStore satisfies CheckpointStore Protocol at runtime
# ---------------------------------------------------------------------------


def test_in_memory_store_is_protocol_compatible() -> None:
    store = InMemoryCheckpointStore()

    # CheckpointStore is @runtime_checkable — isinstance() performs structural check.
    assert isinstance(store, CheckpointStore)
