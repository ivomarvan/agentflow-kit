# Task T020 — JsonFileCheckpointStore + run_until() + resume()

**Epic:** E070 — Checkpointing & Pause/Resume
**Task:** T020

## Goal

Add `JsonFileCheckpointStore` and extend `StateGraphRunner` with `run_until()` and `resume()`.

## Files to read FIRST

1. `src/agentflow/statemachine/checkpoint.py` — T010 output
2. `src/agentflow/statemachine/runner.py` — full BSP loop to understand extension points
3. `src/agentflow/statemachine/resolver.py` — VertexResolver (need lookup_by_name)
4. `src/agentflow/statemachine/topology.py` — StateGraph (access to _resolver)

## Deliverables

| File | Action |
|------|--------|
| `src/agentflow/statemachine/checkpoint.py` | **Modify** — add JsonFileCheckpointStore |
| `src/agentflow/statemachine/runner.py` | **Modify** — add run_until + resume |
| `src/agentflow/statemachine/resolver.py` | **Modify** — add lookup_by_name |
| `src/agentflow/statemachine/__init__.py` | **Modify** — export checkpoint symbols |
| `src/agentflow/tests/statemachine/test_runner_resume.py` | **Create** (5 tests) |

## Implementation

### `JsonFileCheckpointStore`

```python
import dataclasses, json, asyncio
from pathlib import Path

class JsonFileCheckpointStore:
    """Persists checkpoints as JSON files under base_dir/<run_id>/<step:04d>.json.

    State serialization uses dataclasses.asdict(); the __state_type__ field
    stores the fully-qualified class name. Provide state_factory to deserialize.

    Args:
        base_dir: Root directory for checkpoint files.
        state_factory: Optional callable(class_qualname: str, data: dict) -> Any.
                       Required for load() to reconstruct state objects.
    """
    def __init__(
        self,
        base_dir: str | Path = "./checkpoints",
        state_factory: Callable[[str, dict[str, Any]], Any] | None = None,
    ) -> None:
        self._base = Path(base_dir)
        self._state_factory = state_factory

    async def save(self, record: CheckpointRecord) -> None:
        path = self._path(record.run_id, record.step)
        await asyncio.to_thread(path.parent.mkdir, parents=True, exist_ok=True)
        data = {
            "run_id": record.run_id,
            "step": record.step,
            "__state_type__": type(record.state).__qualname__,
            "state": dataclasses.asdict(record.state),
            "active_node_names": record.active_node_names,
        }
        await asyncio.to_thread(path.write_text, json.dumps(data, indent=2), "utf-8")

    async def load(self, run_id: str, step: int) -> CheckpointRecord:
        path = self._path(run_id, step)
        raw = await asyncio.to_thread(path.read_text, "utf-8")
        data = json.loads(raw)
        state_type = data["__state_type__"]
        state = (
            self._state_factory(state_type, data["state"])
            if self._state_factory
            else data["state"]  # return raw dict if no factory
        )
        return CheckpointRecord(
            run_id=run_id,
            step=step,
            state=state,
            active_node_names=data["active_node_names"],
        )

    async def list_steps(self, run_id: str) -> list[int]:
        run_dir = self._base / run_id
        if not run_dir.exists():
            return []
        return sorted(int(p.stem) for p in run_dir.glob("*.json"))

    def _path(self, run_id: str, step: int) -> Path:
        return self._base / run_id / f"{step:04d}.json"
```

### `VertexResolver.lookup_by_name(name) -> StateVertex | None`

```python
def lookup_by_name(self, name: str) -> StateVertex | None:
    """Return the singleton instance for the class with the given __name__, or None."""
    for cls, instance in self._instances.items():
        if cls.__name__ == name:
            return instance
    return None
```

### `StateGraphRunner.run_until()`

```python
async def run_until(
    self,
    initial_state: Any,
    predicate: Callable[[int, Any, list[StateVertex]], bool],
    *,
    store: CheckpointStore,
    run_id: str,
) -> Any:
    """Run BSP loop; save checkpoint after each step; stop when predicate is True.

    Args:
        initial_state: Starting state.
        predicate: (step, state, active_nodes) -> bool. True means pause.
        store: CheckpointStore to persist state after each step.
        run_id: Unique run identifier (used as storage key).

    Returns:
        State at the moment of pausing (or after natural completion).
    """
```

Copy the BSP loop from `run()` and after `on_super_step_end`:
1. Save checkpoint: `await store.save(CheckpointRecord(run_id, step, current_state, [type(n).__name__ for n in active_nodes]))`
2. Check predicate: if `predicate(step, current_state, active_nodes)`: break

### `StateGraphRunner.resume()`

```python
async def resume(
    self,
    store: CheckpointStore,
    run_id: str,
    from_step: int,
) -> Any:
    """Resume from a checkpoint saved by run_until().

    Loads state and active_node_names from the checkpoint, resolves names
    back to StateVertex instances via the graph's VertexResolver,
    then continues the BSP loop.

    Args:
        store: Same CheckpointStore used in run_until().
        run_id: Same run_id used in run_until().
        from_step: Step to resume from (must exist in store).
    """
    record = await store.load(run_id, from_step)
    active_nodes = []
    for name in record.active_node_names:
        vertex = self.graph._resolver.lookup_by_name(name)
        if vertex is None:
            raise ValueError(f"Cannot resolve vertex name {name!r} — is the graph correct?")
        active_nodes.append(vertex)
    # continue the BSP loop from record.state
    ...
```

## Tests (`test_runner_resume.py`, 5 tests)

Use a 3-vertex linear graph: A → B → StdEnd. All FakeVertex subclasses.
State: `@dataclass(frozen=True) class SimpleState: value: int`.

1. `test_run_until_stops_when_predicate_true_at_step_1` — predicate stops at step 1 (after A runs).
2. `test_run_until_saves_checkpoint_per_step` — 1 checkpoint saved after step 1.
3. `test_resume_continues_from_checkpoint` — pause after step 1, resume, verify B ran and state has final value.
4. `test_run_until_completes_normally_when_predicate_always_false` — whole graph runs, 2 checkpoints saved.
5. `test_json_file_store_save_and_load_roundtrip` — uses tmp_path fixture, verifies file written.

## Code quality

```bash
cd /home/ivo/workspace/git.hub.lab.ivo/ai_agents_education
uv run ruff check src/agentflow/statemachine/checkpoint.py src/agentflow/statemachine/runner.py
uv run mypy --strict --follow-imports=skip src/agentflow/statemachine/checkpoint.py
uv run mypy --strict --follow-imports=skip src/agentflow/statemachine/runner.py
uv run pytest src/agentflow/tests/statemachine/test_runner_resume.py -v
uv run pytest src/agentflow/tests/ -v -m "not integration"
```
