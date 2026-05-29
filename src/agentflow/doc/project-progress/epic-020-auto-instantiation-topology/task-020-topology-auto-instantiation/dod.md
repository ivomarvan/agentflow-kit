# DoD — T020 Auto-instantiation in Topology

## Definition of Done

- [x] `Transition.from_node` and `to_target` accept `type[StateVertex] | StateVertex`.
- [x] `Parallel.__init__` accepts `type[StateVertex] | StateVertex` per vertex.
- [x] `Parallel.expand(resolver)` resolves all branches via VertexResolver.
- [x] `StateGraph.__init__` accepts `type[StateVertex] | StateVertex` for `start`.
- [x] `StateGraph._normalize_transitions()` resolves all class references to instances.
- [x] `StateGraph.expand_target()` passes `self._resolver` to `Parallel.expand()`.
- [x] Old `_validate_no_classes()` removed from `StateGraph`.
- [x] All existing topology tests pass (1 renamed, rest unchanged).
- [x] 6 new topology tests pass.
- [x] Full regression suite passes: `pytest src/agentflow/tests/statemachine/ -v`.
- [x] `ruff check` passes clean on `topology.py`.
- [x] `mypy --strict --follow-imports=skip` passes on `topology.py`.
