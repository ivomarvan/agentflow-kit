# Epic E060 — Describable Integration + Live Graph Visualization

**Goal:** Make `StateGraph` a `Describable` subclass so its topology can be rendered as
DOT/SVG/HTML. Add `LiveGraphHooks` that marks active vertices during runtime.
Extend `GraphRenderer` to color active nodes.

**Root:** `src/agentflow/` (not git root)

---

## Scope

| Deliverable | File |
|-------------|------|
| `StateGraph(Describable)` + `get_graph()` | `src/agentflow/statemachine/topology.py` |
| `LiveGraphHooks` | `src/agentflow/statemachine/hooks.py` |
| `GraphRenderer` attribute styling | `src/agentflow/describable/graph_renderer.py` |
| Updated `__init__.py` | `src/agentflow/statemachine/__init__.py` |
| Demo | `src/examples/statemachine_demos/03_live_graph_demo.py` |
| Tests | `src/agentflow/tests/statemachine/test_state_graph_describable.py` |
| Tests | `src/agentflow/tests/statemachine/test_live_graph_hooks.py` |

---

## Task List

| Task | Name | Depends on |
|------|------|-----------|
| T010 | `StateGraph(Describable)` + `get_graph()` override | E010 + E030 done |
| T020 | `LiveGraphHooks` + `GraphRenderer` active-node styling + demo | T010 |

---

## Key Design (from brief §10)

### `StateGraph.get_graph()` output

The graph represents the **transition topology** (not the Describable composition tree):
- **Root Vertex**: `id="StateGraph"`, `label="StateGraph"`, `description={"nodes": count, "transitions": count}`.
- **One Vertex per unique resolved node**: `id=type(node).__name__`, `label=same`, `description={"type": class_name}`.
  - End nodes get `attributes={"is_end": True}`.
- **One Edge per Transition**: `from_id=type(from_node).__name__`, `to_id=type(to_target).__name__`, `label=signal.name`, directed=True.
  - For `Parallel` targets: one Edge per branch vertex (fan-out).
- **Start node**: `attributes={"is_start": True}`.

**Note on node ID uniqueness**: use `type(node).__name__` as ID — sufficient since
`VertexResolver` ensures singleton-per-class. If two distinct instances of the same class
exist (user passed explicit instances), append index: `f"{cls_name}_{i}"`.

### `LiveGraphHooks`

```python
class LiveGraphHooks:
    """RunnerHooks that records active vertices per super-step for visualization.

    Attributes:
        graph: The StateGraph being observed.
        snapshots: list[tuple[int, set[str]]] — (step, {active_vertex_type_names})
                   populated after each super-step.
    """
    def __init__(self, graph: StateGraph) -> None: ...
    # on_super_step_start: add active vertex type names to snapshots
    # on_super_step_end: update latest snapshot with next_active
```

`LiveGraphHooks` fills `snapshots: list[tuple[int, Graph]]` where each `Graph` has
`Vertex.attributes["active"] = True` for the active nodes in that step.

Actually, simpler: store `list[tuple[int, frozenset[str]]]` — step + set of active class names.
Then provide `get_snapshot_graph(step)` → returns `StateGraph.get_graph()` with the active
nodes' vertices marked `attributes["active"] = True`.

### `GraphRenderer` active-node styling

In `to_dot()`, for a vertex with `attributes.get("active", False) == True`:
- Set DOT `fillcolor="#90EE90"` (light green) and `style=filled`.

---

## T010 — `StateGraph(Describable)` + `get_graph()`

**Inputs:**
- `src/agentflow/statemachine/topology.py` — StateGraph (to modify)
- `src/agentflow/describable/describable.py` — Describable base
- `src/agentflow/describable/graph.py` — Graph, Vertex, Edge

**Key changes to `topology.py`:**

1. Import `Describable` at the top (not TYPE_CHECKING — needed for inheritance):
   ```python
   from src.agentflow.describable.describable import Describable
   ```

2. Make `StateGraph` extend `Describable`:
   ```python
   class StateGraph(Describable):
       def __init__(self, start, transitions) -> None:
           super().__init__()  # sets self.name = "StateGraph", self.description from docstring
           ...existing init code...
   ```

3. Override `get_graph()`:
   ```python
   def get_graph(self) -> "Graph":
       from src.agentflow.describable.graph import Edge, Graph, Vertex
       # collect unique nodes
       nodes = self._collect_nodes()  # returns list of unique StateVertex instances
       vertices = [self._vertex_for_node(n) for n in nodes]
       edges = [self._edge_for_transition(t) for t in self._transitions
                for edge in self._edges_for_target(t)]
       root = Vertex(id="StateGraph", label="StateGraph", description={"nodes": len(nodes)})
       root.children = vertices
       return Graph(root=root, edges=edges)
   ```

4. Helper method `_collect_nodes()` — deduplicate nodes from `self._transitions`
   (both `from_node` and resolved `to_target` vertices, including Parallel branches).

**Tests** (`test_state_graph_describable.py`, 4 tests):
1. `test_state_graph_is_describable` — `isinstance(graph, Describable)` is True.
2. `test_get_graph_has_correct_vertex_count` — vertex count matches unique nodes.
3. `test_get_graph_edges_match_transitions` — edge count = transition count (non-Parallel).
4. `test_get_graph_edge_labels_are_signal_names` — edge.label == signal.name.

---

## T020 — `LiveGraphHooks` + `GraphRenderer` styling + demo

**Inputs:**
- `src/agentflow/statemachine/hooks.py` — existing hooks (to add LiveGraphHooks)
- `src/agentflow/describable/graph_renderer.py` — GraphRenderer (to add attribute styling)
- `src/agentflow/statemachine/topology.py` — T010 output
- `src/examples/statemachine_demos/01_brief_example.py` — reference for demo structure

**Changes to `hooks.py`:**
Add `LiveGraphHooks` after `LoggingHooks`:
```python
class LiveGraphHooks:
    def __init__(self, graph: StateGraph) -> None:
        self._graph = graph
        # snapshots: list of (step, frozenset of active vertex class names)
        self.snapshots: list[tuple[int, frozenset[str]]] = []

    def get_snapshot_graph(self, step: int) -> "Graph":
        """Return a Graph with active vertices marked in attributes."""
        # Get step's active names; mark those vertices
        ...
```

**Changes to `graph_renderer.py`:**
In the DOT node-attribute generation: if `vertex.attributes.get("active", False)`:
- Add `fillcolor="#90EE90" style=filled` to the DOT node attributes.

**Demo (`03_live_graph_demo.py`)**:
- Build the brief §2.5 style graph using bare classes.
- Run with `LiveGraphHooks`.
- After run, call `graph.open_graph_browser()` (or save SVG snapshots to `nogit_data/`).
- Shows the visualization capability end-to-end.

**Tests:**

`test_live_graph_hooks.py` (3 tests):
1. `test_live_graph_hooks_records_snapshots` — after run, `len(snapshots) == super_step_count`.
2. `test_live_graph_hooks_marks_active_vertices` — snapshot contains correct active names.
3. `test_graph_renderer_colors_active_node` — `to_dot(graph_with_active_vertex)` contains `fillcolor`.

---

## Definition of Done (Epic Level)

- [ ] `StateGraph` is a `Describable` subclass.
- [ ] `StateGraph.get_graph()` produces topology graph (vertices + edges).
- [ ] `LiveGraphHooks` records snapshots per super-step.
- [ ] `LiveGraphHooks.get_snapshot_graph()` marks active nodes.
- [ ] `GraphRenderer` colors active nodes (fillcolor in DOT output).
- [ ] `LiveGraphHooks` exported from `statemachine/__init__.py`.
- [ ] 7 new tests pass.
- [ ] Demo runs end-to-end (saves SVG or opens browser).
- [ ] Full regression suite passes.
- [ ] `ruff check` + `mypy --strict` pass on modified files.
