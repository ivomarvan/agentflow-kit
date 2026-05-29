# Task T020 — LiveGraphHooks + GraphRenderer Styling + Demo

**Epic:** E060 — Describable Integration
**Task:** T020
**Root:** `src/agentflow/`

## Goal

Add `LiveGraphHooks` to record active vertices per super-step, extend `GraphRenderer`
to color active nodes green in DOT output, and create a demo showing live graph snapshots.

## Context Bundle

- `src/agentflow/statemachine/hooks.py` — add `LiveGraphHooks` after `LoggingHooks`.
- `src/agentflow/statemachine/topology.py` — T010 output (`StateGraph.get_graph()`).
- `src/agentflow/describable/graph_renderer.py` — extend for active-node coloring.
- `src/agentflow/describable/graph.py` — `Graph`, `Vertex`, `Edge`.
- `src/agentflow/statemachine/__init__.py` — export `LiveGraphHooks`.
- `src/examples/statemachine_demos/01_brief_example.py` — demo structure reference.

## Deliverables

| File | Action |
|------|--------|
| `src/agentflow/statemachine/hooks.py` | **Modify** — add `LiveGraphHooks` |
| `src/agentflow/describable/graph_renderer.py` | **Modify** — active-node coloring |
| `src/agentflow/statemachine/__init__.py` | **Modify** — export `LiveGraphHooks` |
| `src/agentflow/tests/statemachine/test_live_graph_hooks.py` | **Create** |
| `src/examples/statemachine_demos/03_live_graph_demo.py` | **Create** |

## Implementation

### `LiveGraphHooks` in `hooks.py`

```python
class LiveGraphHooks:
    """RunnerHooks that records active-node snapshots per super-step.

    After run completes, snapshots contains one entry per super-step
    with the set of active vertex class names.

    Attributes:
        snapshots: list[tuple[int, frozenset[str]]] — (step, active_class_names).
    """

    def __init__(self) -> None:
        self.snapshots: list[tuple[int, frozenset[str]]] = []
        self._current_step: int = 0
        self._current_active: frozenset[str] = frozenset()

    async def on_super_step_start(self, step: int, state: object, active: list[StateVertex]) -> None:
        self._current_step = step
        self._current_active = frozenset(type(n).__name__ for n in active)

    async def on_super_step_end(self, step: int, state: object, next_active: set[StateVertex]) -> None:
        self.snapshots.append((self._current_step, self._current_active))

    # remaining callbacks are no-ops
    async def on_run_start(self, state: object) -> None: ...
    async def on_run_end(self, state: object) -> None: ...
    async def on_vertex_error(self, node: StateVertex, exc: Exception) -> None: ...
    async def on_super_step_results(self, step: int, node_results: list[Any]) -> None: ...

    def get_snapshot_graph(self, graph: "StateGraph", step: int) -> "Graph":
        """Return a copy of graph.get_graph() with active vertices marked.

        Args:
            graph: The StateGraph to visualize.
            step: Step index (1-based) into self.snapshots.

        Returns:
            Graph with active Vertex.attributes["active"] = True.
        """
        import copy
        g = copy.deepcopy(graph.get_graph())
        active_names = self.snapshots[step - 1][1] if step <= len(self.snapshots) else frozenset()
        for v in g.root.children:
            if v.label in active_names:
                v.attributes["active"] = True
        return g
```

### `GraphRenderer` active-node coloring

Read `graph_renderer.py` to find where DOT node attributes are generated.
Add: if `vertex.attributes.get("active", False)` → append `fillcolor="#90EE90" style=filled`
to the node's DOT attributes.

**Example target DOT output for active node:**
```dot
"Research" [label="Research" fillcolor="#90EE90" style=filled tooltip="..."]
```

### Demo (`03_live_graph_demo.py`)

- Build the brief §2.5 style graph (Research → Parallel(WriteIntro, WriteBody) → Review → StdEnd).
- Run with `LiveGraphHooks`.
- After run, for each snapshot in `hooks.snapshots`, call `hooks.get_snapshot_graph(graph, step)`.
- Save HTML output to `nogit_data/graphs/step_{step}.html` (or print DOT to stdout).
- Must be runnable with `python src/examples/statemachine_demos/03_live_graph_demo.py`.

## Tests (`test_live_graph_hooks.py`, 3 tests)

1. `test_live_graph_hooks_records_one_snapshot_per_super_step` — run a 2-step graph; verify `len(snapshots) == 2`.
2. `test_live_graph_hooks_snapshot_contains_active_node_names` — first snapshot has correct vertex name.
3. `test_graph_renderer_colors_active_node_in_dot_output` — `to_dot(graph_with_active_vertex)` contains `fillcolor`.

## Code Quality

```bash
cd /home/ivo/workspace/git.hub.lab.ivo/ai_agents_education
uv run ruff check src/agentflow/statemachine/hooks.py src/agentflow/describable/graph_renderer.py
uv run mypy --strict --follow-imports=skip src/agentflow/statemachine/hooks.py
uv run pytest src/agentflow/tests/statemachine/test_live_graph_hooks.py -v
python src/examples/statemachine_demos/03_live_graph_demo.py
uv run pytest src/agentflow/tests/ -v -m "not integration"
```
