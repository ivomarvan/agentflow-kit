# DoD — E060 T010 StateGraph(Describable)

- [ ] `StateGraph` extends `Describable`.
- [ ] `StateGraph.__init__` calls `super().__init__()` first.
- [ ] `StateGraph.get_graph()` returns a `Graph` with correct vertices and edges.
- [ ] All existing topology tests still pass.
- [ ] 4 new describable tests pass.
- [ ] `ruff check` + `mypy --strict --follow-imports=skip` pass on `topology.py`.
- [ ] Full regression: `pytest src/agentflow/tests/ -v -m "not integration"`.
