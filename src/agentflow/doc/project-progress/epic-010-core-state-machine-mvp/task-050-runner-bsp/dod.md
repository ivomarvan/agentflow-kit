---
apm_category: dod
apm_ref: E010.T050
apm_level: task
created_by: Planner
model: claude-opus-4-7
intended_for: Coder
created_at: 2026-05-28
updated_at: 2026-05-28
---

# Definition of Done: E010.T050 — StateGraphRunner with BSP loop

Coder zaškrtne každý bod po jeho splnění.

## Implementace

- ✅ `src/agentflow/statemachine/runner.py` obsahuje kompletní implementaci (placeholder nahrazen).
- ✅ `StateGraphRunner.__init__` přijímá `graph`, `context`, volitelně `hooks`.
- ✅ `async run(initial_state) -> state` implementováno s BSP smyčkou (Compute → Barrier → Apply → Route).
- ✅ `run_sync(initial_state) -> state` jako `asyncio.run(self.run(...))` wrapper.
- ✅ `_safe_run(node, state)` — try/except, log.exception, hooks.on_vertex_error, vrátí `(StdSignal.fail, _EmptyPatch())`.
- ✅ BSP fáze odpovídají pseudokódu z briefu §3.2 (pořadí: End uzly → gather → apply_patches → route).
- ✅ Set-based join dedupuje vrcholy přes `set[StateVertex]`.

## Exporty

- ✅ `__init__.py` re-exportuje `StateGraphRunner`.
- ✅ Symbol přidán do `__all__`.

## Testy

- ✅ `src/agentflow/tests/statemachine/test_runner_bsp.py` existuje.
- ✅ `test_runner_sequential_two_vertices_runs_to_std_end` ✅
- ✅ `test_runner_parallel_fan_out_runs_both_branches` ✅
- ✅ `test_runner_set_based_join_dedups_same_instance` ✅
- ✅ `test_runner_cycle_terminates_via_std_end_after_n_iterations` ✅
- ✅ `test_runner_vertex_exception_maps_to_std_signal_fail` ✅
- ✅ `test_runner_run_sync_returns_final_state` ✅

## Kvalita kódu

- ✅ Kompletní Google-style docstringy.
- ✅ Žádné relativní importy.

## Verifikace

- ✅ `pytest src/agentflow/tests/statemachine/` — zelené (41/41).
- ✅ `mypy --strict --follow-imports=skip src/agentflow/statemachine/` — zelený (0 issues).
- ✅ `ruff check` — čistý.
- ❌ `ruff format --check` — `topology.py` by bylo přeformátováno, ale je mimo scope T050 (pre-existující issue z T040). Soubory T050 (`runner.py`, `test_runner_bsp.py`) jsou formátově čisté.

## Reporting

- ✅ `report.md` vypracován dle `07-project-management.mdc`.

## Bezpečnostní zábrany

- ✅ **Žádný `git commit/push`** bez explicitního pokynu Human.
