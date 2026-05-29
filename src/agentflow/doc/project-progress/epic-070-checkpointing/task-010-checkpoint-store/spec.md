# Task T010 — CheckpointStore Protocol + InMemoryCheckpointStore

**Epic:** E070 — Checkpointing & Pause/Resume
**Task:** T010

## Goal

Create `checkpoint.py` with the `CheckpointRecord` dataclass, `CheckpointStore` Protocol,
and `InMemoryCheckpointStore` concrete implementation.

## Deliverables

| File | Action |
|------|--------|
| `src/agentflow/statemachine/checkpoint.py` | **Create** |
| `src/agentflow/tests/statemachine/test_checkpoint.py` | **Create** (5 tests) |

## Implementation

```python
# checkpoint.py
from __future__ import annotations
import asyncio
from dataclasses import dataclass
from typing import Any, Protocol

@dataclass
class CheckpointRecord:
    """Snapshot of graph state after one super-step."""
    run_id: str
    step: int
    state: Any
    active_node_names: list[str]  # type(node).__name__ for each active node

class CheckpointStore(Protocol):
    async def save(self, record: CheckpointRecord) -> None: ...
    async def load(self, run_id: str, step: int) -> CheckpointRecord: ...
    async def list_steps(self, run_id: str) -> list[int]: ...

class InMemoryCheckpointStore:
    """In-memory CheckpointStore — for testing and short-lived workflows."""
    def __init__(self) -> None:
        self._data: dict[tuple[str, int], CheckpointRecord] = {}

    async def save(self, record: CheckpointRecord) -> None:
        self._data[(record.run_id, record.step)] = record

    async def load(self, run_id: str, step: int) -> CheckpointRecord:
        try:
            return self._data[(run_id, step)]
        except KeyError:
            raise KeyError(f"No checkpoint: run_id={run_id!r} step={step}") from None

    async def list_steps(self, run_id: str) -> list[int]:
        return sorted(s for (r, s) in self._data if r == run_id)
```

## Tests (5)

```python
@pytest.mark.asyncio
async def test_in_memory_store_save_and_load_roundtrip(): ...
async def test_in_memory_store_load_raises_on_missing_step(): ...
async def test_in_memory_store_list_steps_sorted(): ...
async def test_checkpoint_record_holds_all_fields(): ...
def test_in_memory_store_satisfies_protocol():
    from typing import runtime_checkable
    # static duck-typing check
    store = InMemoryCheckpointStore()
    assert hasattr(store, "save") and hasattr(store, "load") and hasattr(store, "list_steps")
```

## Code quality

```bash
cd /home/ivo/workspace/git.hub.lab.ivo/ai_agents_education
uv run ruff check src/agentflow/statemachine/checkpoint.py
uv run mypy --strict --follow-imports=skip src/agentflow/statemachine/checkpoint.py
uv run pytest src/agentflow/tests/statemachine/test_checkpoint.py -v
```
