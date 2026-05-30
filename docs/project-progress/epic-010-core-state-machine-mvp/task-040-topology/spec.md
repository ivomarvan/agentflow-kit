---
apm_category: task-spec
apm_ref: E010.T040
apm_level: task
created_by: Planner
model: claude-opus-4-7
intended_for: Coder
created_at: 2026-05-28
updated_at: 2026-05-28
---

# Task Specification: E010.T040 — Topology: Transition, Parallel, StateGraph

## 1. Goal

Implementovat tři datové typy pro deklaraci topologie grafu dle briefu §2:
1. **`Transition`** — frozen dataclass popisující hranu `(from_node, signal, to_target)`.
2. **`Parallel`** — fan-out marker uchovávající tuple vrcholů, `expand()` vrátí seznam instancí.
3. **`StateGraph`** — kontejner grafu s metodami pro dotazování topologie: `get_targets`, `expand_target`, `resolve_start`. V tomto Epicu **pouze ručně předané instance** — žádná auto-instanciace (E020).

`StateGraph` také deleguje `apply_patches` na funkci z T020. Pokud je v `transitions` třída (ne instance), vyhodí `TypeError` s popisnou zprávou o E020.

## 2. Inputs

- `src/agentflow/doc/project-progress/brief.md` — §2.1 (Transition), §2.2 (Parallel), §2.3 (auto-inst.), §2.4 (join), §2.5 (kompletní příklad).
- `src/agentflow/doc/project-progress/spec.md` — TD-12 (set-based join + WARNING asymetrie).
- `src/agentflow/doc/project-progress/epic-010-core-state-machine-mvp/plan.md` — sekce T040.
- T020 deliverables: `src/agentflow/statemachine/state.py` (funkce `apply_patches`).
- T030 deliverables: `src/agentflow/statemachine/vertex.py` (`StateVertex`, `End`).
- `pyproject.toml` — konfigurace mypy, pytest.
- `.cursor/rules/10-python.mdc` — Python coding standards.

## 3. Outputs

### 3.1 Modifikované soubory

- `src/agentflow/statemachine/topology.py` — **kompletní implementace** (nahradit placeholder).
- `src/agentflow/statemachine/__init__.py` — přidat `Transition`, `Parallel`, `StateGraph` do re-exportů.

### 3.2 Nové soubory

- `src/agentflow/tests/statemachine/test_topology.py` — 7 unit testů.

### 3.3 Detaily obsahu

#### `topology.py`

```python
"""Transition, Parallel fan-out, and StateGraph topology queries.

Defines the declarative graph structure: Transition edges, Parallel fan-out
markers, and StateGraph which holds the topology and provides query methods
used by StateGraphRunner during the BSP Apply&Route phase.

In Epic E010 only manually instantiated vertices are supported.
Auto-instantiation (VertexResolver singleton-per-class) will be added in E020.
"""

from __future__ import annotations

import dataclasses
import logging
from collections.abc import Sequence
from typing import TYPE_CHECKING

from src.agentflow.statemachine.state import apply_patches
from src.agentflow.statemachine.vertex import StateVertex, End

if TYPE_CHECKING:
    from src.agentflow.statemachine.signal import EnumSignal

_logger = logging.getLogger(__name__)


@dataclasses.dataclass(frozen=True)
class Transition:
    """A directed edge in the state graph.

    Args:
        from_node: Source vertex instance (or End instance).
        signal: Routing signal emitted by from_node.run().
        to_target: Target — a StateVertex instance or a Parallel fan-out.
    """
    from_node: StateVertex
    signal: object  # EnumSignal at runtime — object keeps mypy strict happy
    to_target: StateVertex | "Parallel"


class Parallel:
    """Fan-out marker: activates all contained vertices in the next super-step.

    Args:
        *vertices: StateVertex instances to run in parallel.
    """

    def __init__(self, *vertices: StateVertex) -> None:
        self.vertices: tuple[StateVertex, ...] = vertices

    def expand(self) -> list[StateVertex]:
        """Return all contained vertex instances as a flat list.

        Returns:
            List of StateVertex instances — each will be scheduled for the
            next BSP super-step.
        """
        return list(self.vertices)


class StateGraph:
    """Immutable state graph holding topology and providing query methods.

    Accepts only pre-instantiated StateVertex objects in transitions.
    Passing a class (not an instance) raises TypeError with a helpful message
    pointing to Epic E020 for auto-instantiation support.

    Args:
        start: Starting vertex instance.
        transitions: List of Transition edges defining the graph.

    Raises:
        TypeError: If any transition contains a class rather than an instance.
    """

    def __init__(
        self,
        start: StateVertex,
        transitions: Sequence[Transition],
    ) -> None:
        self._start = start
        self._transitions = list(transitions)
        self._validate_no_classes()

    def _validate_no_classes(self) -> None:
        for t in self._transitions:
            for field_name, node in [("from_node", t.from_node), ("to_target", t.to_target)]:
                if isinstance(node, type):
                    raise TypeError(
                        f"Transition {field_name}={node.__name__!r} is a class, not an instance. "
                        "Auto-instantiation will be added in Epic E020; "
                        "pass an instance (e.g. MyVertex()) for now."
                    )

    def resolve_start(self) -> StateVertex:
        """Return the starting vertex instance.

        Returns:
            The start vertex passed to __init__.
        """
        return self._start

    def get_targets(
        self, node: StateVertex, signal: object
    ) -> list[StateVertex | Parallel]:
        """Return all targets reachable from node via signal.

        Args:
            node: Source vertex whose transitions to search.
            signal: Signal value to match (by identity/equality).

        Returns:
            List of targets (StateVertex or Parallel instances) for matching
            transitions. Empty list if no matching transition found.
        """
        return [
            t.to_target
            for t in self._transitions
            if t.from_node is node and t.signal is signal
        ]

    def expand_target(self, target: StateVertex | Parallel) -> list[StateVertex]:
        """Expand a target to a flat list of concrete vertex instances.

        Args:
            target: Either a single StateVertex or a Parallel fan-out.

        Returns:
            For a StateVertex: [target].
            For a Parallel: result of target.expand().
        """
        if isinstance(target, Parallel):
            return target.expand()
        return [target]

    def apply_patches(self, state: object, patches: Sequence[object]) -> object:
        """Merge patches into a new state instance using per-field reducers.

        Delegates to the standalone apply_patches() function from state.py.

        Args:
            state: Current frozen dataclass state.
            patches: Sequence of StatePatch-like objects.

        Returns:
            New state instance with merged patches.
        """
        return apply_patches(state, patches)  # type: ignore[arg-type]
```

#### `tests/statemachine/test_topology.py` — 7 testů

Použij `FakeVertex` z T070 není dostupný — zde deklarovat jednoduchou ad-hoc třídu v testu:

```python
class _AVertex(StateVertex):
    async def run(self, state, ctx): return (object(), object())

class _BVertex(StateVertex):
    async def run(self, state, ctx): return (object(), object())
```

| # | Test name | Co ověřuje |
|---|-----------|------------|
| 1 | `test_transition_stores_from_signal_to` | Transition ukládá `from_node`, `signal`, `to_target`. |
| 2 | `test_parallel_expand_returns_vertices_list` | `Parallel(a, b).expand()` vrátí `[a, b]`. |
| 3 | `test_state_graph_get_targets_returns_matching_transition_target` | `get_targets(a, sig)` vrátí `[b]`. |
| 4 | `test_state_graph_get_targets_no_match_returns_empty` | Neexistující signal → `[]`. |
| 5 | `test_state_graph_expand_target_parallel_returns_flat_list` | `expand_target(Parallel(a, b))` → `[a, b]`. |
| 6 | `test_state_graph_expand_target_single_vertex_returns_singleton_list` | `expand_target(a)` → `[a]`. |
| 7 | `test_state_graph_rejects_class_in_transitions_with_helpful_error` | `pytest.raises(TypeError, match="E020")`. |

## 4. Context Bundle

### Read (Coder potřebuje)

| Soubor | Proč |
|--------|------|
| `src/agentflow/doc/project-progress/brief.md` | §2.1–§2.5. |
| `src/agentflow/doc/project-progress/spec.md` | TD-12. |
| `src/agentflow/statemachine/state.py` | `apply_patches` funkce (T020). |
| `src/agentflow/statemachine/vertex.py` | `StateVertex`, `End` (T030). |
| `src/agentflow/statemachine/signal.py` | `EnumSignal`, `StdSignal` (T010). |
| `.cursor/rules/10-python.mdc` | Coding standards. |

### Do NOT modify

- `src/agentflow/statemachine/state.py`, `signal.py`, `context.py`, `vertex.py` (hotové tasky).
- `src/agentflow/llm/**`, `src/agentflow/agents/**`, `src/agentflow/tools/**`, `src/agentflow/describable/**`.
- `src/agentflow/doc/**` mimo `task-040-topology/report.md` a `dod.md`.

### Interfaces from prior tasks

```python
from src.agentflow.statemachine.state import apply_patches, UNSET   # T020
from src.agentflow.statemachine.vertex import StateVertex, End       # T030
from src.agentflow.statemachine.signal import EnumSignal, StdSignal  # T010
```

### Interfaces poskytované tímto Taskem pro T050

```python
from src.agentflow.statemachine import Transition, Parallel, StateGraph
# graph.resolve_start() -> StateVertex
# graph.get_targets(node, signal) -> list[StateVertex | Parallel]
# graph.expand_target(target) -> list[StateVertex]
# graph.apply_patches(state, patches) -> state
```

## 5. Dependencies

- T010 ✅ (signal.py)
- T020 ✅ (state.py — `apply_patches`)
- T030 ✅ (vertex.py — `StateVertex`, `End`)

## 6. Test Specification

7 testů v `test_topology.py` — viz sekce 3.3.

**Regresní suite:**
```bash
pytest src/agentflow/tests/statemachine/
mypy --strict --follow-imports=skip src/agentflow/statemachine/
ruff check src/agentflow/statemachine/ src/agentflow/tests/statemachine/
```

## 7. Definition of Done

Viz `dod.md` v tomto adresáři.

## 8. Recommended Coder model

**Composer-2.5 Fast** — datové struktury a query metody, jasně definované API.

## 9. Poznámky pro Coder

- `Transition` jako `@dataclass(frozen=True)` — signál a target jsou pak hashable.
- `get_targets` porovnává `t.from_node is node` (identity) a `t.signal is signal` (identity pro Enum members).
- `_validate_no_classes` kontroluje `isinstance(node, type)` — třída je instance `type`.
- `StateGraph.apply_patches` deleguje na `state.apply_patches` — žádná logika navíc.
- Neimplementuj `VertexResolver` — to je E020.
- Neimplementuj statickou analýzu asymetrie joinu (WARNING) — to je E020.
- Po dokončení: vyplnit `dod.md` + napsat `report.md`. Bez git commitu.
