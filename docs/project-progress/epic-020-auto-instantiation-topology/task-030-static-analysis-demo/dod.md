# DoD — T030 Static Topology Analysis + Demo Update

## Definition of Done

- [ ] `StateGraph._analyze_asymmetric_joins()` exists and is called in `__init__`.
- [ ] Symmetric join graph (§2.5 style) produces no WARNING log messages.
- [ ] Asymmetric join graph produces WARNING with node name and depth info.
- [ ] Linear single-path graph produces no WARNING.
- [ ] `_analyze_asymmetric_joins` handles cycles without infinite loop (visited set).
- [ ] `01_brief_example.py` uses bare classes in all topology definitions.
- [ ] `uv run python examples/quickstart/01_brief_example.py run` exits 0.
- [ ] All 3 new analysis tests pass: `pytest .../test_topology_analysis.py -v`.
- [ ] Full regression suite passes: `pytest src/agentflow/tests/statemachine/ -v`.
- [ ] `ruff check` passes clean on `topology.py`.
- [ ] `mypy --strict --follow-imports=skip` passes on `topology.py`.
