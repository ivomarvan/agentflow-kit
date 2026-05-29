# Task T020 — Auto-instantiation in Topology

**Epic:** E020 — Auto-instantiation & Topology Validation
**Task:** T020
**Root:** `src/agentflow/`

## Goal

Update `Transition`, `Parallel`, and `StateGraph` in `topology.py` to accept bare classes
(subclasses of `StateVertex`) in addition to instances. `StateGraph` auto-instantiates
classes via `VertexResolver` (T010) at graph-build time.

## Context Bundle

- **Brief §2.1–2.3** — Transition/Parallel type widening, singleton-per-class semantics.
- **spec.md TD-05, TD-06** — auto-instantiation, required-defaults error.
- `src/agentflow/statemachine/resolver.py` — T010 output (VertexResolver).
- `src/agentflow/statemachine/topology.py` — current E010 topology (to be modified).
- `src/agentflow/statemachine/vertex.py` — StateVertex, End, StdEnd.
- `src/agentflow/tests/statemachine/test_topology.py` — existing tests to update.

## Deliverables

| File | Action |
|------|--------|
| `src/agentflow/statemachine/topology.py` | **Modify** |
| `src/agentflow/tests/statemachine/test_topology.py` | **Modify + extend** |

## Required Changes

### `Transition` — widen type annotations only
```python
@dataclasses.dataclass(frozen=True)
class Transition:
    from_node: type[StateVertex] | StateVertex
    signal: object
    to_target: type[StateVertex] | StateVertex | Parallel
```
No logic changes; it is a data holder.

### `Parallel.__init__` — widen *vertices type
```python
def __init__(self, *vertices: type[StateVertex] | StateVertex) -> None:
    self.vertices: tuple[type[StateVertex] | StateVertex, ...] = vertices
```

### `Parallel.expand` — add resolver argument
```python
def expand(self, resolver: "VertexResolver") -> list[StateVertex]:
    """Expand and auto-instantiate all branches via resolver.

    Args:
        resolver: VertexResolver for singleton-per-class lookups.

    Returns:
        List of resolved StateVertex instances.
    """
    return [resolver.resolve(v) for v in self.vertices]
```
**Breaking change**: callers of `Parallel.expand()` must pass a resolver.
Update `StateGraph.expand_target()` accordingly.

### `StateGraph.__init__` — create resolver, widen start type, normalize
```python
def __init__(
    self,
    start: type[StateVertex] | StateVertex,
    transitions: Sequence[Transition],
) -> None:
    self._resolver = VertexResolver()
    self._start = self._resolver.resolve(start)
    self._transitions = self._normalize_transitions(transitions)
    # Note: _analyze_asymmetric_joins() will be added in T030
```

### `StateGraph._normalize_transitions` — new private method
- For each `Transition` in the input:
  - `from_node` — resolve via `self._resolver` (class or instance → instance).
  - `to_target` — if `Parallel` → keep as-is (expanded lazily); else resolve via `self._resolver`.
  - Reconstruct a new `Transition` with resolved nodes.
- Return the normalized list.

### `StateGraph.expand_target` — pass resolver to Parallel
```python
def expand_target(self, target: StateVertex | Parallel) -> list[StateVertex]:
    if isinstance(target, Parallel):
        return target.expand(self._resolver)
    return [target]
```

### Remove `StateGraph._validate_no_classes` — no longer needed.

## Tests — update + new (test_topology.py)

**Update existing:**
- `test_state_graph_rejects_class_in_transitions_with_helpful_error`:
  Rename to `test_state_graph_accepts_class_in_transition_auto_resolves`.
  Assert that using a class instead of instance does NOT raise; the resolved node
  `is isinstance` of the given class.

**New tests:**
1. `test_transition_holds_class_without_error` — `Transition(MyVertex, sig, OtherVertex)`
   with both as bare classes constructs without error.
2. `test_parallel_expand_with_resolver` — `Parallel(A, B).expand(resolver)` returns
   two distinct instances, each of the expected type.
3. `test_state_graph_class_based_topology_resolves_start` — `StateGraph(start=MyVertex, ...)`
   returns instance from `resolve_start()`.
4. `test_state_graph_singleton_identity` — two transitions pointing to same class share
   one instance: `graph.resolve_start() is graph.get_targets(...)`.
5. `test_state_graph_class_without_default_raises_value_error` — class with required param
   raises `ValueError` at `StateGraph.__init__` time.
6. `test_state_graph_mixed_class_and_instance` — topology mixing classes and explicit
   instances coexists; instance is returned unchanged.

## Code Quality

- `ruff check src/agentflow/statemachine/topology.py`
- `mypy --strict --follow-imports=skip src/agentflow/statemachine/topology.py`
- `pytest src/agentflow/tests/statemachine/test_topology.py -v`
- Full regression: `pytest src/agentflow/tests/statemachine/ -v` — all green.
