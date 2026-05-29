# Epic E030 — Observability Hooks (Full)

**Goal:** Complete the `RunnerHooks` protocol with `RecorderHooks` and a pytest fixture
`recorded_runner` for asserting over full execution history.

**Root:** `src/agentflow/` (not git root)

---

## Scope

| Deliverable | File |
|-------------|------|
| `SuperStepRecord` dataclass + `RecorderHooks` | `src/agentflow/statemachine/hooks.py` |
| New `on_super_step_results` callback in `RunnerHooks` | `src/agentflow/statemachine/hooks.py` |
| `NoOpHooks` / `LoggingHooks` updated | `src/agentflow/statemachine/hooks.py` |
| Runner updated to call `on_super_step_results` | `src/agentflow/statemachine/runner.py` |
| `recorded_runner` fixture | `src/agentflow/statemachine/testing/fixtures.py` |
| Unit tests for RecorderHooks | `src/agentflow/tests/statemachine/test_recorder_hooks.py` |
| Integration test (§7.3 style) | `src/agentflow/tests/statemachine/test_recorded_runner_fixture.py` |
| Updated `__init__.py` | `src/agentflow/statemachine/__init__.py` |

---

## Task List

| Task | Name | Depends on |
|------|------|-----------|
| T010 | RecorderHooks + protocol extension + runner update | E010 done |
| T020 | `recorded_runner` fixture + integration test | T010 |

### Dependency Graph

```
T010 ──► T020
```

---

## Key Design Decisions

### New callback: `on_super_step_results`

The current protocol lacks a hook that receives per-vertex results (signals + patches).
To support `SuperStepRecord.results`, add:

```python
async def on_super_step_results(
    self,
    step: int,
    node_results: list[tuple[StateVertex, Any, Any]],
) -> None: ...
```

Called in `runner.py` AFTER compute but BEFORE apply, so `RecorderHooks` can capture
raw signals and patches before they are merged.

Runner call site (between lines 87 and 91 in runner.py):
```python
node_results = [
    (node, signal, patch)
    for node, (signal, patch) in zip(active_nodes, results, strict=True)
]
await self.hooks.on_super_step_results(step, node_results)
```

### `SuperStepRecord` structure

```python
@dataclasses.dataclass
class SuperStepRecord:
    step: int
    state_before: object
    active_nodes: list[StateVertex]
    results: list[tuple[StateVertex, Any, Any]]   # (node, signal, patch)
    state_after: object
    next_active: set[StateVertex]
```

`RecorderHooks` builds records incrementally across callbacks:
- `on_super_step_start` → create a partial record (step, state_before, active_nodes)
- `on_super_step_results` → add results to the pending record
- `on_super_step_end` → finalize with state_after and next_active; append to `self.history`

---

## T010 — RecorderHooks + Protocol Extension + Runner Update

**Inputs:**
- `src/agentflow/statemachine/hooks.py` (current: NoOpHooks, LoggingHooks, RunnerHooks)
- `src/agentflow/statemachine/runner.py` (current BSP runner)

**Deliverables:**
1. Add `on_super_step_results` to `RunnerHooks` protocol.
2. Add `on_super_step_results` no-op to `NoOpHooks`.
3. Add `on_super_step_results` log to `LoggingHooks` (DEBUG: node names + signals).
4. Add `SuperStepRecord` dataclass (frozen=False — fields set incrementally).
5. Add `RecorderHooks` class.
6. Update `runner.py` to call `on_super_step_results` after gather, before apply.
7. Export `RecorderHooks`, `SuperStepRecord` from `__init__.py`.

**Tests** (`test_recorder_hooks.py`):
1. `test_recorder_history_length_matches_super_steps` — N-step run → N records.
2. `test_recorder_captures_state_before_and_after` — state_before ≠ state_after when patch changes field.
3. `test_recorder_captures_active_nodes` — active_nodes list matches expected vertices.
4. `test_recorder_captures_results_signals` — results contain correct signal from FakeVertex.
5. `test_recorder_captures_next_active` — next_active set is correct per topology.

---

## T020 — `recorded_runner` Fixture + Integration Test

**Inputs:**
- `src/agentflow/statemachine/testing/fixtures.py`
- `src/agentflow/statemachine/testing/fakes.py`
- `src/agentflow/tests/statemachine/conftest.py`

**Deliverables:**
1. Add `recorded_runner` fixture to `testing/fixtures.py`:
   ```python
   @pytest.fixture
   def recorded_runner(fake_ctx) -> tuple[StateGraphRunner, RecorderHooks]:
       recorder = RecorderHooks()
       def _factory(graph):
           return StateGraphRunner(graph, fake_ctx, hooks=recorder), recorder
       return _factory
   ```
   Note: The fixture returns a factory so the caller can provide the graph.
2. Add fixture to `conftest.py` import.
3. Create `test_recorded_runner_fixture.py` — integration test using a realistic mini-graph
   that demonstrates assertion over `recorder.history` (brief §7.3 pattern).

**Integration test (§7.3 style)**:
- Build a graph: `Research → [rejected 2x] → Review → StdEnd`
- Run with `RecorderHooks`
- Assert:
  - `len(recorder.history)` matches expected number of super-steps
  - `any(isinstance(n, Review) for n in step.active_nodes)` true N times

---

## Definition of Done (Epic Level)

- [ ] `on_super_step_results` added to `RunnerHooks`, `NoOpHooks`, `LoggingHooks`.
- [ ] `SuperStepRecord` and `RecorderHooks` in `hooks.py`.
- [ ] `runner.py` calls `on_super_step_results` after compute, before apply.
- [ ] `recorded_runner` fixture in `testing/fixtures.py`.
- [ ] `RecorderHooks` + `SuperStepRecord` exported from `statemachine/__init__.py`.
- [ ] 5 RecorderHooks unit tests pass.
- [ ] Integration test (§7.3 style) passes.
- [ ] Full regression suite passes: `pytest src/agentflow/tests/statemachine/ -v`.
- [ ] `ruff check` and `mypy --strict` on modified files pass.
