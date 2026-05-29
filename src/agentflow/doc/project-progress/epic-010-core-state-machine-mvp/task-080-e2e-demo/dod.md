---
apm_category: dod
apm_ref: E010.T080
apm_level: task
created_by: Planner
model: claude-opus-4-7
intended_for: Coder
created_at: 2026-05-28
updated_at: 2026-05-28
---

# Definition of Done: E010.T080 — End-to-end demo: brief §2.5 graph

Coder zaškrtne každý bod po jeho splnění.

## Demo skript

- ✅ `src/examples/statemachine_demos/__init__.py` existuje.
- ✅ `src/examples/statemachine_demos/01_brief_example.py` existuje.
- ✅ Demo skript definuje `DemoState`, `DemoPatch`, vrcholy, `CustomSignal`, `StateGraph`.
- ✅ Demo skript je spustitelný: `python -m src.examples.statemachine_demos.01_brief_example` — bez výjimky.
- ✅ Demo skript používá `FakeLlmConnector` a `LoggingHooks`.
- ✅ Demo skript se terminuje v `StdEnd` (ne nekonečná smyčka) — 3 cykly, pak StdEnd.
- ✅ `git_root_to_syspath` použit jako entry-point.

## E2E test

- ✅ `src/agentflow/tests/statemachine/test_e2e_brief_example.py` existuje.
- ✅ `test_brief_example_runs_to_completion` ✅ (+ 2 další testy, všechny zelené).

## Regresní testy

- ✅ `pytest src/agentflow/tests/statemachine/` — zelené (44/44 testů projde).
- ✅ Celá sada spuštěna po dokončení demo skriptu.

## Kvalita kódu

- ✅ Demo skript má docstringy na všech třídách.
- ✅ Žádné relativní importy.

## mypy + ruff

- ✅ `mypy --strict --follow-imports=skip src/agentflow/statemachine/` — zelený (0 errors, 11 files).
- ✅ `ruff check src/agentflow/statemachine/ src/examples/statemachine_demos/` — čistý.

## Reporting

- ✅ `report.md` vypracován dle `07-project-management.mdc`.

## Bezpečnostní zábrany

- ✅ **Žádný `git commit/push`** bez explicitního pokynu Human.
