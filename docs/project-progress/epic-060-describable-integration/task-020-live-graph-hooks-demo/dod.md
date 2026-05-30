# DoD — E060 T020 LiveGraphHooks + GraphRenderer + Demo

- [x] `LiveGraphHooks` exists in `hooks.py`; implements all `RunnerHooks` callbacks.
- [x] `LiveGraphHooks.snapshots` populated after run.
- [x] `LiveGraphHooks.get_snapshot_graph(graph, step)` returns Graph with active nodes marked.
- [x] `GraphRenderer` colors active nodes with `fillcolor="#90EE90" style=filled` in DOT.
- [x] `LiveGraphHooks` exported from `statemachine/__init__.py`.
- [x] All 3 tests pass.
- [x] `03_live_graph_demo.py` runs end-to-end (`python ...` exits 0).
- [x] `ruff check` passes on modified files.
- [x] `mypy --strict --follow-imports=skip` passes on `hooks.py`.
- [x] Full regression: `pytest src/agentflow/tests/ -v -m "not integration"`.
