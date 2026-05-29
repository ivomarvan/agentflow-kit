# Task T010 — RecorderHooks + Protocol Extension + Runner Update

**Epic:** E030 — Observability Hooks (Full)
**Task:** T010
**Root:** `src/agentflow/`

## Goal

Extend `RunnerHooks` protocol with `on_super_step_results`, implement `SuperStepRecord`
and `RecorderHooks` in `hooks.py`, and update `runner.py` to call the new hook.

## Context Bundle

- **Brief §7.1** — RecorderHooks purpose: full super-step history for test assertions.
- **Brief §7.3** — target assertion pattern (uses `step.active`, `step.active_nodes`).
- `src/agentflow/statemachine/hooks.py` — current protocol + NoOpHooks + LoggingHooks.
- `src/agentflow/statemachine/runner.py` — current BSP loop (add hook call here).
- `src/agentflow/statemachine/__init__.py` — update exports.

## Deliverables

| File | Action |
|------|--------|
| `src/agentflow/statemachine/hooks.py` | **Modify** |
| `src/agentflow/statemachine/runner.py` | **Modify** |
| `src/agentflow/statemachine/__init__.py` | **Modify** |
| `src/agentflow/tests/statemachine/test_recorder_hooks.py` | **Create** |

## Implementation Detail

### 1. Add to `RunnerHooks` protocol (hooks.py)

```python
async def on_super_step_results(
    self,
    step: int,
    node_results: list[tuple[StateVertex, Any, Any]],
) -> None:
    """Called after Compute phase, before Apply — provides raw per-vertex results.

    Args:
        step: Super-step counter (1-based).
        node_results: List of (vertex, signal, patch) tuples — one per active vertex.
    """
    ...
```

### 2. Add to `NoOpHooks` (no-op body)

### 3. Add to `LoggingHooks` (DEBUG log with step + signal names)

```python
async def on_super_step_results(
    self,
    step: int,
    node_results: list[tuple[StateVertex, Any, Any]],
) -> None:
    for node, signal, _ in node_results:
        self._logger.debug(
            "vertex_result: step=%d node=%s signal=%s",
            step, type(node).__name__, signal,
        )
```

### 4. `SuperStepRecord` dataclass

Use a regular (not frozen) dataclass since fields are set incrementally:

```python
@dataclasses.dataclass
class SuperStepRecord:
    """Full record of one BSP super-step captured by RecorderHooks.

    Fields set incrementally:
    - on_super_step_start → step, state_before, active_nodes
    - on_super_step_results → results
    - on_super_step_end → state_after, next_active
    """
    step: int
    state_before: object
    active_nodes: list[StateVertex]
    results: list[tuple[StateVertex, Any, Any]] = dataclasses.field(default_factory=list)
    state_after: object = None
    next_active: set[StateVertex] = dataclasses.field(default_factory=set)
```

### 5. `RecorderHooks` class

```python
class RecorderHooks:
    """Records full execution history for post-run assertions in tests.

    Attributes:
        history: List of SuperStepRecord, one per completed super-step.
                 Populated by on_super_step_start/results/end callbacks.
    """

    def __init__(self) -> None:
        self.history: list[SuperStepRecord] = []
        self._pending: dict[int, SuperStepRecord] = {}
```

- `on_super_step_start(step, state, active)` → creates `SuperStepRecord(step, state, list(active))` in `self._pending[step]`.
- `on_super_step_results(step, node_results)` → sets `self._pending[step].results = node_results`.
- `on_super_step_end(step, state, next_active)` → sets `state_after`, `next_active` on pending record; appends to `self.history`; removes from `self._pending`.
- `on_run_start` / `on_run_end` / `on_vertex_error` → no-op (but must exist).

### 6. Update `runner.py` (add hook call)

After the existing line:
```python
results: list[tuple[Any, Any]] = list(await asyncio.gather(...))
```

Add BEFORE `patches = [patch for _, patch in results]`:
```python
node_results = [
    (node, signal, patch)
    for node, (signal, patch) in zip(active_nodes, results, strict=True)
]
await self.hooks.on_super_step_results(step, node_results)
```

### 7. Export from `__init__.py`

Add `RecorderHooks` and `SuperStepRecord` to both `import` statements and `__all__`.

## Tests (`test_recorder_hooks.py`) — 5 tests

Use `FakeVertex`, `make_fake_context`, and `StateGraph` to build a minimal deterministic graph.

1. `test_recorder_history_length_matches_super_steps` — 3-step linear run → 3 records in `history`.
2. `test_recorder_captures_state_before_and_after` — check that `state_before` and `state_after` differ after a patch that changes a field.
3. `test_recorder_captures_active_nodes` — first record's `active_nodes` contains the start vertex.
4. `test_recorder_captures_results_signals` — first record's `results` contains `(start_vertex, expected_signal, ...)`.
5. `test_recorder_captures_next_active` — first record's `next_active` contains the second vertex.

## Code Quality

```bash
cd /home/ivo/workspace/git.hub.lab.ivo/ai_agents_education
uv run ruff check src/agentflow/statemachine/hooks.py src/agentflow/statemachine/runner.py
uv run mypy --strict --follow-imports=skip src/agentflow/statemachine/hooks.py
uv run mypy --strict --follow-imports=skip src/agentflow/statemachine/runner.py
uv run pytest src/agentflow/tests/statemachine/test_recorder_hooks.py -v
uv run pytest src/agentflow/tests/statemachine/ -v
```
