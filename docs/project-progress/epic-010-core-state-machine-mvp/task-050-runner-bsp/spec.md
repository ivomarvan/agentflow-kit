---
apm_category: task-spec
apm_ref: E010.T050
apm_level: task
created_by: Planner
model: claude-opus-4-7
intended_for: Coder
created_at: 2026-05-28
updated_at: 2026-05-28
---

# Task Specification: E010.T050 — StateGraphRunner with BSP loop

## 1. Goal

Implementovat `StateGraphRunner` — jádro execution enginu — per brief §3.2.
Async smyčka se třemi BSP fázemi: Compute (`asyncio.gather`) → Barrier (implicitní v `gather`) →
Apply (`graph.apply_patches`) + Route (set-based join). `_safe_run` mapuje výjimky na
`(StdSignal.fail, StatePatch())`. Convenience `run_sync(state)` wrapper přes `asyncio.run`.

## 2. Inputs

- `src/agentflow/doc/project-progress/brief.md` — §3 (kompletně: §3.1 proč BSP, §3.2 pseudokód, §3.3 hooks).
- `src/agentflow/doc/project-progress/spec.md` — TD-07 (async vrcholy), TD-08 (End semantics), TD-15 (run_sync semantics).
- T020: `src/agentflow/statemachine/state.py` (`apply_patches`, `UNSET`).
- T030: `src/agentflow/statemachine/context.py` + `vertex.py` (`Context`, `StateVertex`, `End`, `StdEnd`).
- T040: `src/agentflow/statemachine/topology.py` (`StateGraph`, `Transition`, `Parallel`).
- T060: `src/agentflow/statemachine/hooks.py` (`RunnerHooks`, `NoOpHooks`).
- T070: `src/agentflow/statemachine/testing/` (`FakeVertex`, `make_fake_context`).
- `pyproject.toml` — pytest konfigurace.
- `.cursor/rules/10-python.mdc` — coding standards.

## 3. Outputs

### 3.1 Modifikované soubory

- `src/agentflow/statemachine/runner.py` — **kompletní implementace** (nahradit placeholder).
- `src/agentflow/statemachine/__init__.py` — přidat `StateGraphRunner` do re-exportů.

### 3.2 Nové soubory

- `src/agentflow/tests/statemachine/test_runner_bsp.py` — 6 unit testů.

### 3.3 Detaily obsahu

#### `runner.py`

```python
"""StateGraphRunner — BSP super-step execution loop.

Implements the Bulk Synchronous Parallel (BSP) model:
  Compute (parallel via asyncio.gather)
  → Barrier (implicit in gather)
  → Apply (per-field reducer merge)
  → Route (set-based implicit join)

The loop terminates when all active nodes are End instances.
Vertex exceptions are caught by _safe_run and mapped to StdSignal.fail.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from src.agentflow.statemachine.hooks import NoOpHooks, RunnerHooks
from src.agentflow.statemachine.signal import StdSignal
from src.agentflow.statemachine.vertex import End, StateVertex
from src.agentflow.statemachine.topology import StateGraph
from src.agentflow.statemachine.context import Context

_logger = logging.getLogger(__name__)


class StateGraphRunner:
    """Executes a StateGraph using the Bulk Synchronous Parallel (BSP) model.

    Args:
        graph: StateGraph instance defining topology and transitions.
        context: Shared services injected into each vertex.
        hooks: Optional observability callbacks; defaults to NoOpHooks.
    """

    def __init__(
        self,
        graph: StateGraph,
        context: Context,
        hooks: RunnerHooks | None = None,
    ) -> None:
        self.graph = graph
        self.context = context
        self.hooks: RunnerHooks = hooks or NoOpHooks()  # type: ignore[assignment]

    async def run(self, initial_state: Any) -> Any:
        """Execute the graph from initial_state until an End node is reached.

        BSP loop: for each super-step, all active non-End vertices run in
        parallel (Compute), results are gathered (Barrier), state patches
        are merged (Apply), and next active nodes are determined (Route).

        End vertices are run last in each step; the loop terminates once
        only End vertices remain.

        Args:
            initial_state: Starting frozen dataclass state.

        Returns:
            Final state after the last super-step (after End node ran).
        """
        current_state = initial_state
        active_nodes: list[StateVertex] = [self.graph.resolve_start()]
        step = 0

        await self.hooks.on_run_start(current_state)

        while active_nodes:
            # Run End nodes if present — they run last, then we stop
            end_nodes = [n for n in active_nodes if isinstance(n, End)]
            for end in end_nodes:
                await self._safe_run(end, current_state)
            active_nodes = [n for n in active_nodes if not isinstance(n, End)]
            if not active_nodes:
                break

            step += 1
            await self.hooks.on_super_step_start(step, current_state, active_nodes)

            # --- PHASE 1: COMPUTE (parallel) ---
            results: list[tuple[Any, Any]] = await asyncio.gather(
                *(self._safe_run(node, current_state) for node in active_nodes)
            )

            # --- PHASE 2: BARRIER already happened (gather synchronizes) ---

            # --- PHASE 3A: APPLY (per-field reducers) ---
            patches = [patch for _, patch in results]
            current_state = self.graph.apply_patches(current_state, patches)

            # --- PHASE 3B: ROUTE (set-based implicit join) ---
            next_set: set[StateVertex] = set()
            for node, (signal, _) in zip(active_nodes, results):
                for target in self.graph.get_targets(node, signal):
                    for vertex in self.graph.expand_target(target):
                        next_set.add(vertex)

            await self.hooks.on_super_step_end(step, current_state, next_set)
            active_nodes = list(next_set)

        await self.hooks.on_run_end(current_state)
        return current_state

    def run_sync(self, initial_state: Any) -> Any:
        """Synchronous entry point — runs the entire graph in a new event loop.

        Convenience method for CLI scripts and Jupyter notebooks that do not
        manage an event loop themselves. Uses asyncio.run() internally.
        Semantics differ from Context.run_sync(): this runs the WHOLE graph,
        while Context.run_sync wraps a single blocking callable in to_thread.

        Args:
            initial_state: Starting frozen dataclass state.

        Returns:
            Final state after the last super-step.
        """
        return asyncio.run(self.run(initial_state))

    async def _safe_run(
        self, node: StateVertex, state: Any
    ) -> tuple[Any, Any]:
        """Execute a vertex with exception handling.

        Maps any unexpected exception to (StdSignal.fail, empty patch)
        so that a single vertex failure does not crash the entire super-step.

        Args:
            node: Vertex to execute.
            state: Current state snapshot.

        Returns:
            Tuple (signal, patch). On exception: (StdSignal.fail, _EmptyPatch()).
        """
        try:
            return await node.run(state, self.context)
        except Exception as exc:
            _logger.exception(
                "Vertex failed: node=%s exc_type=%s",
                type(node).__name__, type(exc).__name__,
            )
            await self.hooks.on_vertex_error(node, exc)
            from src.agentflow.statemachine.vertex import _EmptyPatch
            return StdSignal.fail, _EmptyPatch()
```

**Poznámka k `_EmptyPatch`:** T030 definuje `_EmptyPatch` jako interní sentinel v `vertex.py`.
`_safe_run` ho importuje pro případ exception path. V T080 se testy stavají s reálnými `StatePatch`
instancemi.

#### `tests/statemachine/test_runner_bsp.py` — 6 testů

Testy používají `FakeVertex` z T070, `make_fake_context`, `StdEnd`, `StateGraph`, `Transition`, `Parallel`.

Pro jednoduchost stavu v testech: definuj lokálně `@dataclass(frozen=True) class TestState: pass` nebo použij `object()` — runner nemusí mít specifický typ stavu.

| # | Test name | Co ověřuje |
|---|-----------|------------|
| 1 | `test_runner_sequential_two_vertices_runs_to_std_end` | `A → B → StdEnd`, runner doběhne. |
| 2 | `test_runner_parallel_fan_out_runs_both_branches` | `A → Parallel(B, C) → StdEnd`, B i C běžely. |
| 3 | `test_runner_set_based_join_dedups_same_instance` | dvě větve → stejná instance `Review`, Review běžel jen jednou (citač). |
| 4 | `test_runner_cycle_terminates_via_std_end_after_n_iterations` | cyklus `A → A` (po N iteracích → StdEnd). |
| 5 | `test_runner_vertex_exception_maps_to_std_signal_fail` | vrchol vyhodí, runner pokračuje přes `StdSignal.fail` transition. |
| 6 | `test_runner_run_sync_returns_final_state` | `runner.run_sync(state)` vrátí finální state. |

**Tip pro test 3 (set-based join):**
```python
review = FakeVertex(StdSignal.ok, empty_patch)
# Dvě větve obě směřují na tutéž instanci `review`
transitions = [
    Transition(write_intro, StdSignal.ok, review),
    Transition(write_body, StdSignal.ok, review),
    Transition(review, StdSignal.ok, std_end),
]
```
Po Compute fázi kde běžely `write_intro` a `write_body`, `next_set` bude `{review}` (ne `{review, review}`).

**Tip pro test 4 (cycle):**
```python
counter = [0]
def make_loop_vertex():
    # po 2 volání přepne na StdSignal.done (přejde na StdEnd)
    ...
```
Nebo jednodušší: `FakeVertex` s alternativním signálem po N voláních — ale `FakeVertex` je jednoduchý.
Lepší: dvě `FakeVertex` instance — `a_ok` přejde na sebe N-krát, pak jiný signál přejde na StdEnd.
Anebo: `FakeVertex` vracející vždy `fail`, transition `A → fail → StdEnd`.

## 4. Context Bundle

### Read (Coder potřebuje)

| Soubor | Proč |
|--------|------|
| `src/agentflow/doc/project-progress/brief.md` | §3 kompletně (BSP pseudokód). |
| `src/agentflow/doc/project-progress/spec.md` | TD-07, TD-08, TD-15. |
| `src/agentflow/statemachine/topology.py` | StateGraph API (T040). |
| `src/agentflow/statemachine/vertex.py` | StateVertex, End, StdEnd, _EmptyPatch (T030). |
| `src/agentflow/statemachine/context.py` | Context (T030). |
| `src/agentflow/statemachine/hooks.py` | RunnerHooks, NoOpHooks (T060). |
| `src/agentflow/statemachine/state.py` | apply_patches (T020). |
| `src/agentflow/statemachine/testing/` | FakeVertex, make_fake_context (T070). |
| `.cursor/rules/10-python.mdc` | Coding standards. |

### Do NOT modify

- Cokoli mimo `runner.py`, `__init__.py`, `test_runner_bsp.py`.
- `src/agentflow/doc/**` mimo `task-050-runner-bsp/report.md` a `dod.md`.

### Interfaces from prior tasks

```python
from src.agentflow.statemachine.topology import StateGraph, Transition, Parallel  # T040
from src.agentflow.statemachine.vertex import StateVertex, End, StdEnd, _EmptyPatch  # T030
from src.agentflow.statemachine.context import Context  # T030
from src.agentflow.statemachine.hooks import RunnerHooks, NoOpHooks  # T060
from src.agentflow.statemachine.state import apply_patches  # T020
from src.agentflow.statemachine.signal import StdSignal  # T010
from src.agentflow.statemachine.testing import FakeVertex, make_fake_context  # T070
```

### Interfaces poskytované tímto Taskem pro T080

```python
from src.agentflow.statemachine import StateGraphRunner
# runner.run(initial_state) -> final_state (async)
# runner.run_sync(initial_state) -> final_state (sync wrapper)
```

## 5. Dependencies

- T020 ✅, T030 ✅, T040 ✅, T060 ✅, T070 ✅

## 6. Test Specification

6 testů v `test_runner_bsp.py` — viz sekce 3.3.

**Regresní suite:**
```bash
pytest src/agentflow/tests/statemachine/
mypy --strict --follow-imports=skip src/agentflow/statemachine/
ruff check src/agentflow/statemachine/ src/agentflow/tests/statemachine/
```

## 7. Definition of Done

Viz `dod.md` v tomto adresáři.

## 8. Recommended Coder model

**claude-sonnet-4-6** — jádro frameworku, komplexní async logika, kritické testy.

## 9. Poznámky pro Coder

- BSP pseudokód z briefu §3.2 je závazný — implementace musí odpovídat pořadí fází.
- `End` uzly se zpracovávají **před** výpočtem nového super-kroku — runner je zahrne do iterace, spustí jejich `run()`, ale pak je vyloučí z dalšího plánování.
- `next_set` je `set[StateVertex]` — automaticky dedupuje díky object identity (set-based join).
- `_safe_run` musí volat `hooks.on_vertex_error` PŘED vracením `(StdSignal.fail, ...)`.
- `run_sync` používá `asyncio.run()` — nelze volat z již běžícího event loopu (Jupyter). To je known limitation; zmínit v docstringu.
- mypy strict: `hooks: RunnerHooks | None = None` → `self.hooks = hooks or NoOpHooks()` může vyžadovat `# type: ignore[assignment]` pokud mypy nerozpozná Protocol kompatibilitu. Coder řeší na místě.
- Po dokončení: vyplnit `dod.md` + napsat `report.md`. Bez git commitu.
