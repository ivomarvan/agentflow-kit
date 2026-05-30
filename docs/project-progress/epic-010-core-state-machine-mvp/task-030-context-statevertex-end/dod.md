---
apm_category: dod
apm_ref: E010.T030
apm_level: task
created_by: Planner
model: claude-opus-4-7
intended_for: Coder
created_at: 2026-05-28
updated_at: 2026-05-28
---

# Definition of Done: E010.T030 — Context + StateVertex + End/StdEnd

Coder zaškrtne každý bod po jeho splnění.

## Implementace

- ✅ `src/agentflow/statemachine/context.py` obsahuje kompletní implementaci (placeholder nahrazen).
- ✅ `Context` dataclass má pole: `connector`, `tools` (optional), `logger` (default), `run_id` (auto uuid).
- ✅ `Context.run_sync(fn, *args, **kwargs)` implementován jako `asyncio.to_thread` wrapper.
- ✅ `src/agentflow/statemachine/vertex.py` obsahuje kompletní implementaci (placeholder nahrazen).
- ✅ `StateVertex(ABC)` s abstractmethod `async run(state, ctx)` implementován.
- ✅ `End(StateVertex)` jako marker subclass implementován.
- ✅ `StdEnd(End)` vracející `StdSignal.done` implementován.
- ✅ Circular import vyřešen (`if TYPE_CHECKING:` nebo ekvivalentní řešení).

## Exporty

- ✅ `src/agentflow/statemachine/__init__.py` re-exportuje `Context`, `StateVertex`, `End`, `StdEnd`.
- ✅ Všechny 4 symboly přidány do `__all__`.

## Testy

- ✅ `src/agentflow/tests/statemachine/test_context.py` existuje.
- ✅ `test_context_run_sync_executes_sync_callable` ✅
- ✅ `test_context_run_id_is_unique_per_instance` ✅
- ✅ `test_context_default_logger_named_statemachine` ✅
- ✅ `src/agentflow/tests/statemachine/test_vertex_endings.py` existuje.
- ✅ `test_state_vertex_is_abstract` ✅
- ✅ `test_std_end_returns_done_and_empty_patch` ✅
- ✅ `test_end_subclass_detected_by_isinstance` ✅

## Kvalita kódu

- ✅ Všechny veřejné třídy a metody mají Google-style docstring.
- ✅ Žádné relativní importy.
- ✅ `from __future__ import annotations` použito tam kde pomáhá.
- ✅ `_EmptyPatch` není v `__all__` (interní sentinel).

## Verifikace

- ✅ `pytest src/agentflow/tests/statemachine/` — 16 testů zelených (3 T010 + 6 nových T030 + 7 T060/T020 z jiných tasků).
- ❌ `mypy --strict --follow-imports=skip src/agentflow/statemachine/` — 4 pre-existující chyby v `state.py` (T020 scope, nelze upravit). Soubory T030 (`context.py`, `vertex.py`, `__init__.py`) jsou čisté — `mypy --strict` na nich hlásí Success.
- ❌ `ruff check src/agentflow/statemachine/ src/agentflow/tests/statemachine/` — 4 pre-existující chyby v `state.py` a `test_state_reducers.py` (mimo T030 scope). Soubory T030 jsou čisté.
- ✅ `ruff format --check` na souborech T030 — čistý.

## Reporting

- ✅ `report.md` v tomto adresáři vypracován dle `07-project-management.mdc` (sekce 1–6).

## Bezpečnostní zábrany

- ✅ **Žádný `git commit/push`** proveden bez explicitního pokynu Human.
- ✅ **Žádné mazání** souborů mimo cíl tasku.
