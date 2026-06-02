# Task T030 — Static Topology Analysis + Demo Update

**Epic:** E020 — Auto-instantiation & Topology Validation
**Task:** T030
**Root:** `src/agentflow/`

## Goal

Add `_analyze_asymmetric_joins()` static analysis to `StateGraph` and update
`01_brief_example.py` to use the new class-based topology API.

## Context Bundle

- **Brief §2.4** — asymmetric-join warning semantics and example message.
- **Brief §2.5** — reference graph (§2.5 is symmetric → no warning expected).
- `src/agentflow/statemachine/topology.py` — T020 output (VertexResolver-enabled).
- `src/examples/statemachine_demos/01_brief_example.py` — demo to update.

## Deliverables

| File | Action |
|------|--------|
| `src/agentflow/statemachine/topology.py` | **Modify** — add `_analyze_asymmetric_joins()` |
| `src/examples/statemachine_demos/01_brief_example.py` | **Modify** — use classes |
| `src/agentflow/tests/statemachine/test_topology_analysis.py` | **Create** |

## Algorithm — `_analyze_asymmetric_joins`

Call this method at the END of `StateGraph.__init__` (after `_normalize_transitions`).

```python
def _analyze_asymmetric_joins(self) -> None:
    """Warn about nodes with incoming edges from branches of different depth."""
```

Steps:
1. **Build adjacency** — iterate `self._transitions`; for each transition build:
   - `successors: dict[StateVertex, list[StateVertex]]` — node → list of next nodes.
   - `in_edges: dict[StateVertex, list[StateVertex]]` — node → list of predecessor nodes.
   For `Parallel` targets, expand them with `self._resolver`.
   Start node is the implicit entry point.

2. **Find multi-in nodes** — nodes where `len(in_edges[node]) > 1`.

3. **For each multi-in node**, find the **nearest common ancestor fan-out** by:
   - BFS backwards from each incoming predecessor until a common ancestor is found or
     we reach the start node.
   - Compute BFS distance from the common ancestor to each predecessor.

4. **If path lengths differ**, emit:
   ```python
   _logger.warning(
       "Node %r has %d incoming transitions from branches of different depths "
       "(%s). It may run multiple times per cycle. If barrier semantics are "
       "needed, ensure branch symmetry or use an explicit Join (not yet "
       "implemented).",
       node.__class__.__name__,
       len(preds),
       ", ".join(f"{p.__class__.__name__}=depth{d}" for p, d in zip(preds, depths)),
   )
   ```

**Note on cycles:** The §2.5 graph contains `Review → Research` cycle. The BFS must
handle cycles gracefully (use a `visited` set to avoid infinite loops). Cycle detection
only matters for the backwards BFS — forward edges can still be re-traversed for the join
analysis on a per-ancestor-search basis.

## Demo Update — `01_brief_example.py`

Replace all vertex instances with bare classes everywhere:
- `start=Research()` → `start=Research`
- `Transition(research, ...)` → `Transition(Research, ...)`
- `Parallel(write_intro, write_body)` → `Parallel(WriteIntro, WriteBody)`
- etc.

Remove any local variable assignments for vertex instances (e.g. `research = Research()`).
Verify the script produces the same output as before — run it.

## Tests (`test_topology_analysis.py`)

**Fixtures** — define minimal vertex classes (no fields, all-default `__init__`):
```python
class NodeA(StateVertex): ...
class NodeB(StateVertex): ...
class NodeC(StateVertex): ...
```

1. `test_symmetric_join_no_warning` (caplog):
   Graph: `A → Parallel(B, C) → D`; both B and C have depth 1 from A.
   Assert `WARNING` NOT in log records at WARNING level for NodeD.

2. `test_asymmetric_join_emits_warning` (caplog):
   Graph: `A → Parallel(B, C) → D`; B goes directly to D, C goes through E then D.
   Depths from A: B→D=2, C→E→D=3.
   Assert `WARNING` in log records containing `"NodeD"` (or equivalent class name).

3. `test_single_incoming_no_warning` (caplog):
   Linear graph: `A → B → C`.
   Assert no WARNING emitted.

## Code Quality

- `ruff check src/agentflow/statemachine/topology.py`
- `mypy --strict --follow-imports=skip src/agentflow/statemachine/topology.py`
- `pytest src/agentflow/tests/statemachine/test_topology_analysis.py -v`
- Run demo: `uv run python examples/quickstart/01_brief_example.py run` — exits 0.
- Full regression: `pytest src/agentflow/tests/statemachine/ -v` — all green.
