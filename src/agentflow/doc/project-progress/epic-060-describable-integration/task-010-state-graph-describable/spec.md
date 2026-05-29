# Task T010 — StateGraph(Describable) + get_graph()

**Epic:** E060 — Describable Integration
**Task:** T010
**Root:** `src/agentflow/`

## Goal

Make `StateGraph` a `Describable` subclass and override `get_graph()` to produce
a topology graph (vertices = nodes, edges = transitions with signal labels).

## Context Bundle

- **brief §10** — E060 integration plan.
- `src/agentflow/statemachine/topology.py` — `StateGraph` (to modify).
- `src/agentflow/describable/describable.py` — `Describable` base.
- `src/agentflow/describable/graph.py` — `Graph`, `Vertex`, `Edge` dataclasses.
- `src/agentflow/tests/statemachine/test_topology.py` — existing topology tests (must still pass).

## Deliverables

| File | Action |
|------|--------|
| `src/agentflow/statemachine/topology.py` | **Modify** — StateGraph extends Describable |
| `src/agentflow/tests/statemachine/test_state_graph_describable.py` | **Create** |

## Implementation

### Key changes to `topology.py`

1. **Import Describable** (top-level, not TYPE_CHECKING — needed for inheritance):
   ```python
   from src.agentflow.describable.describable import Describable
   ```

2. **`StateGraph(Describable)` class header**

3. **Update `__init__`** — call `super().__init__()` FIRST:
   ```python
   def __init__(self, start, transitions) -> None:
       super().__init__()   # Describable sets self.name, self.description
       self._resolver = VertexResolver()
       ...rest unchanged...
   ```

4. **Override `get_graph()`**:
   ```python
   def get_graph(self) -> "Graph":
       """Build a topology Graph: one Vertex per node, one Edge per transition."""
       from src.agentflow.describable.graph import Edge, Graph, Vertex
       nodes = self._collect_topology_nodes()
       node_ids = {id(n): type(n).__name__ for n in nodes}
       # handle name collisions (two instances of same class)
       ...
       vertices = [self._make_node_vertex(n, node_ids, is_start=(n is self._start)) for n in nodes]
       edges = self._make_topology_edges(node_ids)
       root = Vertex(
           id="StateGraph",
           label="StateGraph",
           description={"nodes": len(nodes), "transitions": len(self._transitions)},
           children=vertices,
       )
       return Graph(root=root, edges=edges)
   ```

5. **`_collect_topology_nodes()`** — private method:
   - Collect all unique vertex instances (from `self._start` + all `from_node` and resolved `to_target` in transitions).
   - For `Parallel` targets: expand via `self._resolver` to get all vertices.
   - Return deduplicated list preserving order.

6. **`_make_node_vertex(node, node_ids, is_start)`** — creates `Vertex(id=node_ids[id(node)], label=..., description=..., attributes={"is_start": ...})`.

7. **`_make_topology_edges(node_ids)`** — iterates `self._transitions`:
   - `from_id = node_ids[id(t.from_node)]`
   - If `t.to_target` is a `Parallel`: expand → one Edge per branch.
   - Else: single Edge.
   - `label = t.signal.name` (use `getattr(t.signal, "name", str(t.signal))`).

### ID collision handling

If two different instances have the same class name (user passed explicit instances),
generate unique IDs: `f"{cls_name}_{i}"` where `i` is the sequential index among same-name nodes.

## Tests (`test_state_graph_describable.py`, 4 tests)

Build a minimal graph using `FakeVertex` (or simple inline vertex classes):

1. `test_state_graph_is_describable_instance`
2. `test_get_graph_root_has_correct_node_count`
3. `test_get_graph_edges_count_matches_transitions`
4. `test_get_graph_edge_labels_are_signal_names`

## Code Quality

```bash
cd /home/ivo/workspace/git.hub.lab.ivo/ai_agents_education
uv run ruff check src/agentflow/statemachine/topology.py
uv run mypy --strict --follow-imports=skip src/agentflow/statemachine/topology.py
uv run pytest src/agentflow/tests/statemachine/test_state_graph_describable.py -v
uv run pytest src/agentflow/tests/ -v -m "not integration"
```

**IMPORTANT**: All existing topology tests must still pass after this change.
