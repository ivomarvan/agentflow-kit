# DoD — T010 VertexResolver

## Definition of Done

- [x] `src/agentflow/statemachine/resolver.py` exists and is importable.
- [x] `VertexResolver.resolve(instance)` returns the same object (identity).
- [x] `VertexResolver.resolve(SomeClass)` returns an instance of `SomeClass`.
- [x] `VertexResolver.resolve(SomeClass)` called twice returns the same instance (`id()` match).
- [x] `VertexResolver.resolve(ClassWithRequiredParam)` raises `ValueError` with informative message.
- [x] `VertexResolver.clear()` causes next `resolve(SomeClass)` to create a NEW instance.
- [x] `ruff check` passes with no errors on `resolver.py`.
- [x] `mypy --strict --follow-imports=skip` passes on `resolver.py`.
- [x] All 5 unit tests pass: `pytest src/agentflow/tests/statemachine/test_resolver.py -v`.
- [x] Full regression suite passes: `pytest src/agentflow/tests/statemachine/ -v`.
