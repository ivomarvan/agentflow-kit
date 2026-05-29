---
apm_category: dod
apm_ref: E010.T020
apm_level: task
created_by: Planner
model: claude-opus-4-7
intended_for: Coder
created_at: 2026-05-28
updated_at: 2026-05-28
---

# Definition of Done: E010.T020 — State, StatePatch & per-field reducery

Coder zaškrtne každý bod po jeho splnění.

## Implementace

- ✅ `src/agentflow/statemachine/state.py` obsahuje kompletní implementaci (placeholder nahrazen).
- ✅ Funkce `apply_patches(state, patches)` implementována a dokumentována (Google-style docstring).
- ✅ Helper `extract_reducer(annotated_type)` implementován (vrací callable nebo `None`).
- ✅ Konstanta `UNSET = object()` definována jako sentinel pro „nesetuj".
- ✅ Extrakce reduceru z `Annotated[T, reducer]` funguje pro `Annotated[tuple, operator.add]`.
- ✅ WARNING emitován při kolizi 2+ patchů na poli bez reduceru.
- ✅ `None` v patchi = „nenastavovat" (konvence z briefu §1.1).
- ✅ `UNSET` v patchi = „nenastavovat" (sentinel konvence).

## Exporty

- ✅ `src/agentflow/statemachine/__init__.py` re-exportuje `apply_patches` a `UNSET`.
- ✅ Obojí přidáno do `__all__`.

## Testy

- ✅ `src/agentflow/tests/statemachine/test_state_reducers.py` existuje.
- ✅ `test_apply_patches_uses_reducer_for_annotated_field` ✅
- ✅ `test_apply_patches_max_reducer_keeps_higher_score` ✅
- ✅ `test_apply_patches_no_reducer_last_writer_wins` ✅
- ✅ `test_apply_patches_no_reducer_warns_on_collision` ✅
- ✅ `test_apply_patches_skips_none_value_in_patch` ✅
- ✅ `test_apply_patches_returns_new_instance` ✅
- ✅ `test_apply_patches_empty_patch_list_returns_same_state` ✅

## Kvalita kódu

- ✅ Všechny veřejné symboly mají Google-style docstring.
- ✅ Žádné relativní importy — jen absolutní `from src.agentflow...`.
- ✅ `from __future__ import annotations` použito.
- ✅ Žádné zbytečné TODO/FIXME v implementačním kódu.

## Verifikace

- ✅ `pytest src/agentflow/tests/statemachine/` — vše zelené (23/23 testů).
- ✅ `mypy --strict --follow-imports=skip src/agentflow/statemachine/` — zelený.
- ✅ `ruff check src/agentflow/statemachine/ src/agentflow/tests/statemachine/` — čistý.
- ✅ `ruff format --check src/agentflow/statemachine/ src/agentflow/tests/statemachine/` — čistý.

## Reporting

- ✅ `report.md` v tomto adresáři vypracován dle `07-project-management.mdc` (sekce 1–6).

## Bezpečnostní zábrany

- ✅ **Žádný `git commit/push`** proveden bez explicitního pokynu Human.
- ✅ **Žádné mazání** souborů mimo cíl tasku.
