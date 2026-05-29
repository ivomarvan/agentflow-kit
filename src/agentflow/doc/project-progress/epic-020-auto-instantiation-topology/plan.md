# Epic E020 — Auto-instantiation & Topology Validation

**Goal:** Introduce `VertexResolver` (singleton-per-class), allow writing classes instead of instances
in topology, validate constructor parameters at graph-build time, and perform static analysis of
asymmetric join topologies with `logging.warning`.

**Root:** `src/agentflow/` (not git root)

---

## Scope

| Deliverable | File |
|-------------|------|
| `VertexResolver` | `src/agentflow/statemachine/resolver.py` (new) |
| Updated `Transition`, `Parallel`, `StateGraph` | `src/agentflow/statemachine/topology.py` |
| Static topology analysis | `src/agentflow/statemachine/topology.py` (`_analyze_asymmetric_joins`) |
| Updated `__init__.py` | `src/agentflow/statemachine/__init__.py` |
| Updated demo (class-based) | `src/examples/statemachine_demos/01_brief_example.py` |
| Unit tests | `src/agentflow/tests/statemachine/` |

---

## Task List

| Task | Name | Depends on | Coder |
|------|------|-----------|-------|
| T010 | VertexResolver | E010 done | — |
| T020 | Auto-instantiation in topology | T010 | — |
| T030 | Static topology analysis + demo | T020 | — |

### Dependency Graph

```
T010 ──► T020 ──► T030
```

---

## Key Technical Decisions

From `spec.md`:
- **TD-05** Singleton-per-class auto-instantiation via internal `VertexResolver`.
- **TD-06** Auto-instantiation requires all constructor params to have default values; clear error at graph-build time without defaults.
- **TD-12** Implicit set-join with `WARNING` on asymmetry.

---

## T010 — VertexResolver

**Goal:** Standalone `VertexResolver` class in `resolver.py`.

**Inputs:** `src/agentflow/statemachine/vertex.py` (StateVertex)

**Outputs:** `src/agentflow/statemachine/resolver.py`

**Interface:**
```python
class VertexResolver:
    def resolve(self, v: type[StateVertex] | StateVertex) -> StateVertex:
        """Return existing instance or auto-instantiate (singleton-per-class)."""

    def clear(self) -> None:
        """Remove all cached instances — use in tests for isolation."""
```

**Validation (inside `resolve` for class inputs):**
- Use `inspect.signature(cls)` to check all parameters have defaults.
- If any parameter lacks a default: raise `ValueError` with message:
  `"Cannot auto-instantiate {cls.__name__}: parameter '{name}' has no default value. "
   "Add a default or pass an instance directly."`

**Tests** (`test_resolver.py`):
1. `test_resolve_instance_returned_unchanged` — passing an instance returns the same object.
2. `test_resolve_class_creates_instance` — first resolve of a class returns a new instance.
3. `test_resolve_class_is_singleton` — second resolve returns identical instance (same `id()`).
4. `test_resolve_class_without_default_raises` — class with required param raises `ValueError`.
5. `test_clear_resets_cache` — after `clear()`, resolve creates a fresh instance.

---

## T020 — Auto-instantiation in topology

**Goal:** Update `Transition`, `Parallel`, `StateGraph` to accept classes in addition to instances.

**Inputs:**
- `src/agentflow/statemachine/resolver.py` (T010 output)
- `src/agentflow/statemachine/topology.py` (current E010 state)

**Changes to `topology.py`:**

1. **`Transition` type annotations** — widen `from_node` and `to_target`:
   ```python
   @dataclasses.dataclass(frozen=True)
   class Transition:
       from_node: type[StateVertex] | StateVertex
       signal: object
       to_target: type[StateVertex] | StateVertex | Parallel
   ```

2. **`Parallel.__init__`** — widen `*vertices` type:
   ```python
   def __init__(self, *vertices: type[StateVertex] | StateVertex) -> None:
   ```

3. **`Parallel.expand`** — now takes `resolver`:
   ```python
   def expand(self, resolver: VertexResolver) -> list[StateVertex]:
       return [resolver.resolve(v) for v in self.vertices]
   ```

4. **`StateGraph.__init__`** — widen `start` type; create `VertexResolver`; normalize all
   transitions to instances:
   ```python
   def __init__(
       self,
       start: type[StateVertex] | StateVertex,
       transitions: Sequence[Transition],
   ) -> None:
       self._resolver = VertexResolver()
       self._start = self._resolver.resolve(start)
       self._transitions = self._normalize_transitions(transitions)
   ```
   - Remove old `_validate_no_classes()` method (classes are now accepted).
   - Add `_normalize_transitions()` — iterates over transitions, resolves `from_node`; leaves
     `to_target` that are `Parallel` as-is (expanded lazily by `expand_target()`); resolves
     `to_target` that are classes/instances.

5. **`StateGraph.expand_target`** — pass resolver to `Parallel.expand`:
   ```python
   def expand_target(self, target: StateVertex | Parallel) -> list[StateVertex]:
       if isinstance(target, Parallel):
           return target.expand(self._resolver)
       return [target]
   ```

6. `StateGraph.resolve_start()` — no change needed (already resolves in `__init__`).

**Tests** (`test_topology.py` — update + new):
- **Update** existing test `test_state_graph_rejects_class_in_transitions_with_helpful_error`:
  now classes are ACCEPTED — test should verify class is auto-resolved to instance.
- New: `test_transition_accepts_class` — `Transition(MyVertex, signal, OtherVertex)` with classes.
- New: `test_parallel_expand_with_resolver` — `Parallel(A, B).expand(resolver)` returns instances.
- New: `test_state_graph_class_based_topology` — full mini-graph using only classes.
- New: `test_state_graph_singleton_identity` — two transitions pointing to the same class share one instance.
- New: `test_state_graph_class_without_default_raises_value_error` — missing default → `ValueError`.
- New: `test_state_graph_mixed_class_and_instance` — classes and instances can coexist.

---

## T030 — Static topology analysis + demo

**Goal:** Add `_analyze_asymmetric_joins()` to `StateGraph`; update demo to use classes.

**Inputs:**
- `src/agentflow/statemachine/topology.py` (T020 output)
- `src/examples/statemachine_demos/01_brief_example.py`

**Algorithm:**
1. Build a dict `in_transitions: dict[StateVertex, list[Transition]]` — for each resolved
   `to_target` vertex, collect all transitions pointing to it.
2. For nodes with `len(in_transitions[node]) > 1`:
   a. Find the nearest common fan-out ancestor(s) — traverse backwards using
      `from_node → to_target` edges to find `Parallel`-originated predecessors.
   b. Compute path length from each incoming `from_node` back to the fan-out predecessor.
   c. If path lengths differ, emit:
      ```
      logging.warning(
          "Node %r has %d incoming transitions from branches of different depths "
          "(%s). It may run multiple times. If barrier semantics are needed, "
          "ensure branch symmetry or use an explicit Join (not yet implemented).",
          node.__class__.__name__, len(in_transitions[node]), depth_info,
      )
      ```
3. Simple case detection (must work for the §2.5 example graph):
   - `Review` has 2 incoming edges from `WriteIntro` and `WriteBody`, both depth 1 from their
     common fan-out. → **no warning** (symmetric).
   - If one branch had an extra step → **warning**.

**Demo update** (`01_brief_example.py`):
- Change all `Research()`, `WriteIntro()`, etc. to bare classes `Research`, `WriteIntro`, etc.
- Change `start=Research()` to `start=Research`.
- Verify the script still runs end-to-end and produces the same output.

**Tests** (`test_topology_analysis.py`):
1. `test_symmetric_join_no_warning` — standard §2.5 graph emits no WARNING.
2. `test_asymmetric_join_emits_warning` — extra node on one branch triggers WARNING.
3. `test_single_incoming_no_warning` — single-path graph produces no warnings.

---

## Definition of Done (Epic Level)

- [ ] `resolver.py` exists with `VertexResolver` passing all 5 unit tests.
- [ ] `topology.py` accepts classes in `Transition`, `Parallel`, `StateGraph`; all new tests pass.
- [ ] `_analyze_asymmetric_joins()` emits WARNING for asymmetric join; no false positives.
- [ ] `01_brief_example.py` uses classes and runs end-to-end without errors.
- [ ] `VertexResolver` exported from `statemachine/__init__.py`.
- [ ] Full regression suite (`pytest src/agentflow/tests/statemachine/`) passes green.
- [ ] `ruff check` and `mypy --strict` on `src/agentflow/statemachine/` pass clean.
