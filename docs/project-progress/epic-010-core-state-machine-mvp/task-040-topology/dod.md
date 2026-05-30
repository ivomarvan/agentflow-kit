---
apm_category: dod
apm_ref: E010.T040
apm_level: task
created_by: Planner
model: claude-opus-4-7
intended_for: Coder
created_at: 2026-05-28
updated_at: 2026-05-28
---

# Definition of Done: E010.T040 — Topology: Transition, Parallel, StateGraph

Coder zaškrtne každý bod po jeho splnění.

## Implementace

- ✅ `src/agentflow/statemachine/topology.py` obsahuje kompletní implementaci (placeholder nahrazen).
- ✅ `Transition` je `@dataclass(frozen=True)` s poli `from_node`, `signal`, `to_target`.
- ✅ `Parallel` drží `tuple[StateVertex, ...]`, metoda `expand()` vrátí `list[StateVertex]`.
- ✅ `StateGraph.__init__` přijímá `start` a `transitions`; validuje, že nejsou třídy.
- ✅ `StateGraph.resolve_start()` vrátí start vertex.
- ✅ `StateGraph.get_targets(node, signal)` vrátí list cílů pro daný uzel+signál.
- ✅ `StateGraph.expand_target(target)` rozbalí `Parallel` nebo vrátí `[single_vertex]`.
- ✅ `StateGraph.apply_patches(state, patches)` deleguje na `state.apply_patches`.
- ✅ `TypeError` s textem "E020" nebo "auto-instantiation" vyhazován při třídě v transitions.

## Exporty

- ✅ `__init__.py` re-exportuje `Transition`, `Parallel`, `StateGraph`.
- ✅ Všechny 3 symboly v `__all__`.

## Testy

- ✅ `src/agentflow/tests/statemachine/test_topology.py` existuje.
- ✅ `test_transition_stores_from_signal_to` ✅
- ✅ `test_parallel_expand_returns_vertices_list` ✅
- ✅ `test_state_graph_get_targets_returns_matching_transition_target` ✅
- ✅ `test_state_graph_get_targets_no_match_returns_empty` ✅
- ✅ `test_state_graph_expand_target_parallel_returns_flat_list` ✅
- ✅ `test_state_graph_expand_target_single_vertex_returns_singleton_list` ✅
- ✅ `test_state_graph_rejects_class_in_transitions_with_helpful_error` ✅

## Kvalita kódu

- ✅ Všechny veřejné třídy a metody mají Google-style docstring.
- ✅ Žádné relativní importy.
- ✅ `from __future__ import annotations` použito.

## Verifikace

- ✅ `pytest src/agentflow/tests/statemachine/` — zelené (30/30).
- ✅ `mypy --strict --follow-imports=skip src/agentflow/statemachine/` — zelený.
- ✅ `ruff check` + `ruff format --check` — čistý.

## Reporting

- ✅ `report.md` v tomto adresáři vypracován dle `07-project-management.mdc`.

## Bezpečnostní zábrany

- ✅ **Žádný `git commit/push`** bez explicitního pokynu Human.
