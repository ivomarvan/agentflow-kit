# DoD — T020 `recorded_runner` Fixture + Integration Test

## Definition of Done

- [x] `recorded_runner` fixture exists in `testing/fixtures.py` and returns a factory callable.
- [x] `conftest.py` imports `recorded_runner` so it is available in all statemachine tests.
- [x] `test_recorded_runner_fixture.py` contains 3 integration tests.
- [x] `test_recorded_runner_history_has_correct_length` passes.
- [x] `test_recorded_runner_active_nodes_sequence` passes.
- [x] `test_recorded_runner_state_evolves_across_steps` passes.
- [x] Full regression suite passes: `pytest src/agentflow/tests/statemachine/ -v`.
- [x] `ruff check` passes on modified files.
- [x] `mypy --strict --follow-imports=skip` passes on `testing/fixtures.py`.
