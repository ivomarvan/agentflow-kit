# DoD — E070 T020 JsonFileCheckpointStore + run_until + resume

- [ ] `JsonFileCheckpointStore` added to `checkpoint.py`.
- [ ] `VertexResolver.lookup_by_name()` added to `resolver.py`.
- [ ] `StateGraphRunner.run_until()` implemented.
- [ ] `StateGraphRunner.resume()` implemented.
- [ ] All 4 symbols exported from `statemachine/__init__.py`.
- [ ] All 5 unit tests pass.
- [ ] `ruff check` passes on modified files.
- [ ] `mypy --strict --follow-imports=skip` passes on `checkpoint.py` and `runner.py`.
- [ ] Full regression: `pytest src/agentflow/tests/ -v -m "not integration"`.
