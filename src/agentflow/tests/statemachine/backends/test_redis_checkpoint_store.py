"""Integration tests for RedisCheckpointStore.

Requires: docker compose up -d  (redis service)
          uv pip install -e ".[redis-backend]"
Run with: pytest -m integration

Environment:
    REDIS_URL: override default  (default: redis://localhost:6379)
"""

from __future__ import annotations

import dataclasses
import os
import uuid
from collections.abc import AsyncGenerator

import pytest

from agentflow.statemachine.backends.redis_checkpoint_store import RedisCheckpointStore
from agentflow.statemachine.checkpoint import CheckpointRecord

_DEFAULT_URL = "redis://localhost:6379"


@dataclasses.dataclass(frozen=True)
class _TestState:
    value: str
    count: int = 0


def _state_factory(qualname: str, data: dict[str, object]) -> _TestState:
    return _TestState(**data)  # type: ignore[arg-type]


@pytest.fixture
async def store() -> AsyncGenerator[RedisCheckpointStore, None]:
    """Connected RedisCheckpointStore, torn down after each test."""
    url = os.environ.get("REDIS_URL", _DEFAULT_URL)
    async with RedisCheckpointStore(url, state_factory=_state_factory) as s:
        yield s


@pytest.mark.integration
@pytest.mark.asyncio
async def test_save_and_load_roundtrip(store: RedisCheckpointStore) -> None:
    """Save a record and load it back — fields must match."""
    run_id = f"test_{uuid.uuid4().hex[:8]}"
    state = _TestState(value="hello", count=42)
    record = CheckpointRecord(
        run_id=run_id, step=1, state=state, active_node_names=["NodeA"]
    )

    await store.save(record)
    loaded = await store.load(run_id, 1)

    assert loaded.run_id == run_id
    assert loaded.step == 1
    assert loaded.state == state
    assert loaded.active_node_names == ["NodeA"]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_list_steps(store: RedisCheckpointStore) -> None:
    """Save 3 steps out of order and verify list_steps returns them sorted."""
    run_id = f"test_{uuid.uuid4().hex[:8]}"
    for step in [3, 1, 2]:
        rec = CheckpointRecord(
            run_id=run_id,
            step=step,
            state=_TestState(value=f"s{step}"),
            active_node_names=[],
        )
        await store.save(rec)

    steps = await store.list_steps(run_id)
    assert steps == [1, 2, 3]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_load_missing_raises_keyerror(store: RedisCheckpointStore) -> None:
    """Loading a non-existent checkpoint raises KeyError."""
    with pytest.raises(KeyError, match="No checkpoint"):
        await store.load(f"no_such_{uuid.uuid4().hex}", 99)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_overwrite_same_step(store: RedisCheckpointStore) -> None:
    """Saving the same (run_id, step) twice replaces the record."""
    run_id = f"test_{uuid.uuid4().hex[:8]}"
    first = CheckpointRecord(
        run_id=run_id, step=1, state=_TestState("first"), active_node_names=[]
    )
    second = CheckpointRecord(
        run_id=run_id, step=1, state=_TestState("second"), active_node_names=["X"]
    )

    await store.save(first)
    await store.save(second)
    loaded = await store.load(run_id, 1)

    assert loaded.state == _TestState("second")
    assert loaded.active_node_names == ["X"]
