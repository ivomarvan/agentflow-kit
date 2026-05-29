# DoD — T010 RecorderHooks + Protocol Extension + Runner Update

## Definition of Done

- [ ] `RunnerHooks` protocol has `on_super_step_results(step, node_results)` method.
- [ ] `NoOpHooks` has `on_super_step_results` (no-op).
- [ ] `LoggingHooks` has `on_super_step_results` (DEBUG per-vertex log).
- [ ] `SuperStepRecord` dataclass exists in `hooks.py` with all 6 fields.
- [ ] `RecorderHooks` exists and implements all 6 `RunnerHooks` callbacks.
- [ ] `RecorderHooks.history` is populated after a run.
- [ ] `runner.py` calls `self.hooks.on_super_step_results(step, node_results)` after compute, before apply.
- [ ] `RecorderHooks` and `SuperStepRecord` exported from `statemachine/__init__.py`.
- [ ] All 5 unit tests pass: `pytest .../test_recorder_hooks.py -v`.
- [ ] Full regression suite passes: `pytest src/agentflow/tests/statemachine/ -v`.
- [ ] `ruff check` passes on modified files.
- [ ] `mypy --strict --follow-imports=skip` passes on `hooks.py` and `runner.py`.
