# Task T020 — `recorded_runner` Fixture + Integration Test

**Epic:** E030 — Observability Hooks (Full)
**Task:** T020
**Root:** `src/agentflow/`

## Goal

Add a `recorded_runner` pytest fixture to `testing/fixtures.py` and write an
integration test demonstrating assertion over `recorder.history` (brief §7.3 style).

## Context Bundle

- **Brief §7.2** — fixture signatures.
- **Brief §7.3** — example test with `history` assertions.
- `src/agentflow/statemachine/testing/fixtures.py` — existing `fake_ctx`, `make_state_graph` fixtures.
- `src/agentflow/statemachine/testing/fakes.py` — FakeVertex, make_fake_context.
- `src/agentflow/statemachine/hooks.py` — RecorderHooks, SuperStepRecord (T010 output).
- `src/agentflow/tests/statemachine/conftest.py` — imports fixtures.

## Deliverables

| File | Action |
|------|--------|
| `src/agentflow/statemachine/testing/fixtures.py` | **Modify** — add `recorded_runner` |
| `src/agentflow/tests/statemachine/conftest.py` | **Modify** — import new fixture |
| `src/agentflow/tests/statemachine/test_recorded_runner_fixture.py` | **Create** |

## `recorded_runner` Fixture Design

The fixture should return a FACTORY (callable), not a pre-built runner, since the graph
must be passed at test time:

```python
@pytest.fixture
def recorded_runner(fake_ctx):
    """Factory fixture: given a StateGraph, returns (runner, recorder) pair.

    Usage:
        def test_something(recorded_runner, fake_ctx):
            runner, recorder = recorded_runner(my_graph)
            runner.run_sync(initial_state)
            assert len(recorder.history) == expected

    Returns:
        Callable[[StateGraph], tuple[StateGraphRunner, RecorderHooks]]
    """
    def _factory(graph: StateGraph) -> tuple[StateGraphRunner, RecorderHooks]:
        recorder = RecorderHooks()
        return StateGraphRunner(graph, fake_ctx, hooks=recorder), recorder
    return _factory
```

## Integration Test (`test_recorded_runner_fixture.py`)

Build a realistic mini-graph using `FakeVertex`:

**Graph:** `A --ok--> B --ok--> C(StdEnd)` (3-step linear run):
- Step 1: A runs, emits ok → B becomes active
- Step 2: B runs, emits ok → C (StdEnd) becomes active
- Step 3: StdEnd runs (End node), loop exits

(End nodes are run but NOT counted as a super-step in the runner, so expect 2 records.)

Read `runner.py` to confirm whether End nodes are counted in `on_super_step_start`
(they are processed separately, outside the super-step counter).

**Tests:**
1. `test_recorded_runner_history_has_correct_length` — run the 3-node graph; check
   `len(recorder.history)` matches the number of non-End super-steps.
2. `test_recorded_runner_active_nodes_sequence` — check that `history[0].active_nodes`
   contains vertex A, and `history[1].active_nodes` contains vertex B.
3. `test_recorded_runner_state_evolves_across_steps` — use a state with a counter field
   and a patch that increments it; check `history[i].state_after` has the expected count.

## Code Quality

```bash
cd /home/ivo/workspace/git.hub.lab.ivo/ai_agents_education
uv run ruff check src/agentflow/statemachine/testing/fixtures.py
uv run mypy --strict --follow-imports=skip src/agentflow/statemachine/testing/fixtures.py
uv run pytest src/agentflow/tests/statemachine/test_recorded_runner_fixture.py -v
uv run pytest src/agentflow/tests/statemachine/ -v
```
