# DoD — E050 T010 ToolCallVertex + LlmTurnVertex

- [x] `src/agentflow/statemachine/adapters/` directory exists with `__init__.py`.
- [x] `ToolCallVertex` implemented; all `__init__` params have defaults except the three callables.
- [x] `LlmTurnVertex` implemented; uses `ctx.connector.achat()`.
- [x] Both classes exported from `adapters/__init__.py`.
- [x] All 6 unit tests pass.
- [x] `ruff check` passes on adapter files.
- [x] `mypy --strict --follow-imports=skip` passes on adapter files.
- [x] Full regression: `pytest src/agentflow/tests/ -v -m "not integration"`.
