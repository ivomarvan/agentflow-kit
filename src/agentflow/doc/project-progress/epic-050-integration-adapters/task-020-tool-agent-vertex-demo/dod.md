# DoD — E050 T020 ToolAgentVertex + Demo

- [x] `ToolAgentVertex` implemented; calls `await agent.arun(question)`.
- [x] All 3 adapters exported from `adapters/__init__.py`.
- [x] All 3 adapters exported from `statemachine/__init__.py`.
- [x] 2 unit tests for `ToolAgentVertex` pass.
- [x] `02_tool_agent_demo.py` runs end-to-end (`python ...` exits 0, prints answer).
- [x] `ruff check` passes on all adapter files.
- [x] `mypy --strict --follow-imports=skip` passes on `tool_agent_vertex.py`.
- [x] Full regression: `pytest src/agentflow/tests/ -v -m "not integration"` — 157 passed (2 pre-existing failures in test_live_graph_hooks.py from a different epic, unrelated to T020).
