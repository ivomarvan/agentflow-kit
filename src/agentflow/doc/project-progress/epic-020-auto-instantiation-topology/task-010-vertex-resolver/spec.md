# Task T010 — VertexResolver

**Epic:** E020 — Auto-instantiation & Topology Validation
**Task:** T010
**Root:** `src/agentflow/`

## Goal

Implement `VertexResolver` — a per-graph singleton registry that maps
`type[StateVertex]` → `StateVertex` instance. Allows users to reference classes
(not instances) in graph topology; the framework auto-instantiates on first use.

## Context Bundle

- **Brief §2.3** — singleton-per-class semantics, Flyweight pattern.
- **spec.md TD-05** — auto-instantiation via internal `VertexResolver`.
- **spec.md TD-06** — requires default values for all constructor params; clear error otherwise.
- `src/agentflow/statemachine/vertex.py` — `StateVertex` ABC.

## Deliverables

| File | Action |
|------|--------|
| `src/agentflow/statemachine/resolver.py` | **Create** |
| `src/agentflow/tests/statemachine/test_resolver.py` | **Create** |

## Implementation

```python
# Pattern: Flyweight (GoF) — one instance per class within a graph lifetime.
class VertexResolver:
    """Singleton-per-class registry for StateVertex auto-instantiation.

    Args: none (created per-StateGraph).
    """

    def __init__(self) -> None:
        self._store: dict[type[StateVertex], StateVertex] = {}

    def resolve(self, v: type[StateVertex] | StateVertex) -> StateVertex:
        """Return v if it is already an instance; otherwise auto-instantiate.

        Args:
            v: A StateVertex instance or a subclass of StateVertex.

        Returns:
            StateVertex instance — either v itself or the cached/new instance.

        Raises:
            ValueError: If v is a class whose __init__ has parameters without defaults.
        """

    def clear(self) -> None:
        """Remove all cached instances — for test isolation."""
```

**Validation inside `resolve` for class input:**
- `inspect.signature(cls)` — skip `self`.
- If any param lacks a default: raise `ValueError`:
  `f"Cannot auto-instantiate {cls.__name__}: parameter '{name}' has no default value. "
   "Add a default or pass an instance directly."`

## Tests (5 cases)

1. `test_resolve_instance_returned_unchanged` — `isinstance` → same object returned.
2. `test_resolve_class_creates_instance` — class → returns instance of that class.
3. `test_resolve_class_is_singleton` — second `resolve` returns `id()`-identical object.
4. `test_resolve_class_without_default_raises` — class with required param → `ValueError`.
5. `test_clear_resets_cache` — after `clear()`, next resolve creates a fresh instance.

## Code Quality

- `ruff check src/agentflow/statemachine/resolver.py`
- `mypy --strict --follow-imports=skip src/agentflow/statemachine/resolver.py`
- `pytest src/agentflow/tests/statemachine/test_resolver.py -v`
- Full regression: `pytest src/agentflow/tests/statemachine/ -v` — all green.
