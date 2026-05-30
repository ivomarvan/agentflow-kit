# Epic E070 — Checkpointing & Pause/Resume

**Goal:** Pluggable persistence of state after each super-step enabling pause/resume
and human-in-the-loop workflows.

**Root:** `src/agentflow/`

---

## Scope

| Deliverable | File |
|-------------|------|
| `CheckpointStore` Protocol | `src/agentflow/statemachine/checkpoint.py` |
| `InMemoryCheckpointStore` | same file |
| `JsonFileCheckpointStore` | same file |
| `StateGraphRunner.run_until()` | `src/agentflow/statemachine/runner.py` |
| `StateGraphRunner.resume()` | same file |
| Human-in-the-loop example | `src/examples/statemachine_demos/04_human_in_the_loop_demo.py` |
| Export update | `src/agentflow/statemachine/__init__.py` |
| Tests | `src/agentflow/tests/statemachine/test_checkpoint.py` |
| Tests | `src/agentflow/tests/statemachine/test_runner_resume.py` |

---

## Task List

| Task | Name | Depends on |
|------|------|-----------|
| T010 | `CheckpointStore` Protocol + `InMemoryCheckpointStore` | E010 done |
| T020 | `JsonFileCheckpointStore` + `run_until()` + `resume()` | T010 |
| T030 | Human-in-the-loop demo | T020 |

---

## Design

### `CheckpointStore` Protocol (`checkpoint.py`)

```python
@dataclass
class CheckpointRecord:
    """Serializable snapshot of one super-step."""
    run_id: str
    step: int
    state: Any                   # frozen dataclass state
    active_node_names: list[str] # type(node).__name__ for each active node

class CheckpointStore(Protocol):
    async def save(self, record: CheckpointRecord) -> None: ...
    async def load(self, run_id: str, step: int) -> CheckpointRecord: ...
    async def list_steps(self, run_id: str) -> list[int]: ...
```

### `InMemoryCheckpointStore`

Dict-based, stores objects directly (no serialization needed).
```python
class InMemoryCheckpointStore:
    def __init__(self) -> None:
        self._data: dict[tuple[str, int], CheckpointRecord] = {}
```

### `JsonFileCheckpointStore`

- Path: `<base_dir>/<run_id>/<step:04d>.json`
- Serialization: `dataclasses.asdict(state)` + `state.__class__.__qualname__`
  stored in JSON, deserialized via a `state_factory: Callable[[str, dict], Any]`
  parameter on `__init__`. This callback receives `(class_qualname, data_dict)`.
- File I/O: `asyncio.to_thread(json.dump / json.load)`.

```python
class JsonFileCheckpointStore:
    def __init__(
        self,
        base_dir: str | Path = "./checkpoints",
        state_factory: Callable[[str, dict[str, Any]], Any] | None = None,
    ) -> None: ...
```

### `StateGraphRunner.run_until(predicate, initial_state, store, run_id)`

```python
async def run_until(
    self,
    initial_state: Any,
    predicate: Callable[[int, Any, list[StateVertex]], bool],
    *,
    store: CheckpointStore,
    run_id: str,
) -> Any:
    """Run BSP loop, save checkpoint after each step, stop when predicate is True.

    Predicate signature: (step: int, state: Any, active_nodes: list[StateVertex]) -> bool.
    When predicate returns True, the loop pauses and the current state is returned.
    Use runner.resume() with the same store/run_id to continue.
    """
```

### `StateGraphRunner.resume(store, run_id, from_step)`

```python
async def resume(
    self,
    store: CheckpointStore,
    run_id: str,
    from_step: int,
) -> Any:
    """Resume execution from a saved checkpoint.

    Loads CheckpointRecord(run_id, from_step), resolves active_node_names
    back to StateVertex instances via the graph's VertexResolver,
    then continues the BSP loop from the saved state.
    """
```

**Resolving active_node_names → StateVertex:**
Use `graph._resolver.resolve(cls)` where `cls` is found by looking up `type.__name__`
in the resolver's registry via `graph._resolver._instances` (or expose a `lookup_by_name(name)` method on `VertexResolver`).

---

## T010 — `CheckpointStore` Protocol + `InMemoryCheckpointStore`

**Inputs:**
- `src/agentflow/statemachine/runner.py` — existing runner (read-only, for context)

**Deliverables:**
1. Create `src/agentflow/statemachine/checkpoint.py` with `CheckpointRecord`, `CheckpointStore`, `InMemoryCheckpointStore`.
2. Create `src/agentflow/tests/statemachine/test_checkpoint.py` (5 tests).

**Tests (`test_checkpoint.py`):**
1. `test_in_memory_store_save_and_load_roundtrip`
2. `test_in_memory_store_load_raises_on_missing_step`
3. `test_in_memory_store_list_steps`
4. `test_checkpoint_record_fields`
5. `test_checkpoint_store_is_protocol` — verify `InMemoryCheckpointStore` satisfies the Protocol

---

## T020 — `JsonFileCheckpointStore` + `run_until()` + `resume()`

**Inputs:**
- `src/agentflow/statemachine/checkpoint.py` — T010 output
- `src/agentflow/statemachine/runner.py` — extend with run_until + resume
- `src/agentflow/statemachine/resolver.py` — VertexResolver (may need `lookup_by_name`)

**Deliverables:**
1. Extend `src/agentflow/statemachine/checkpoint.py` with `JsonFileCheckpointStore`.
2. Modify `src/agentflow/statemachine/runner.py` — add `run_until()` and `resume()` methods.
3. Extend `src/agentflow/statemachine/resolver.py` — add `lookup_by_name(name) -> StateVertex | None`.
4. Create `src/agentflow/tests/statemachine/test_runner_resume.py` (5 tests).
5. Modify `src/agentflow/statemachine/__init__.py` — export `CheckpointStore`, `CheckpointRecord`, `InMemoryCheckpointStore`, `JsonFileCheckpointStore`.

**Tests (`test_runner_resume.py`):**
1. `test_run_until_stops_at_predicate_step`
2. `test_run_until_saves_checkpoint_per_step`
3. `test_resume_continues_from_checkpoint`
4. `test_run_until_completes_normally_when_predicate_never_true`
5. `test_json_file_store_roundtrip` — save + load with simple frozen dataclass state

---

## T030 — Human-in-the-loop demo

**Inputs:** T020 output.

**Deliverable:** `src/examples/statemachine_demos/04_human_in_the_loop_demo.py`

**Demo design:**
- 3-vertex graph: `Draft` → `Review` (waits for human approval) → `Publish` → StdEnd.
- `Draft` produces a text. `Review` echoes current draft text and "waits" (simulated).
- Use `run_until(predicate=lambda step, state, active: "Review" in [type(n).__name__ for n in active])`.
- Simulate human approval: modify state with approved=True.
- `resume()` from the saved checkpoint with the updated state.
- Print progress at each stage.
- Uses `FakeLlmConnector` / `InMemoryCheckpointStore` — no external dependencies.

---

## Definition of Done (Epic Level)

- [ ] `CheckpointStore`, `CheckpointRecord`, `InMemoryCheckpointStore`, `JsonFileCheckpointStore` in `checkpoint.py`.
- [ ] All 4 symbols exported from `statemachine/__init__.py`.
- [ ] `runner.run_until()` and `runner.resume()` implemented.
- [ ] 10 unit tests pass.
- [ ] `04_human_in_the_loop_demo.py` runs end-to-end (exit 0).
- [ ] `ruff check` + `mypy --strict` pass on new/modified files.
- [ ] Full regression: `pytest src/agentflow/tests/ -v -m "not integration"`.
