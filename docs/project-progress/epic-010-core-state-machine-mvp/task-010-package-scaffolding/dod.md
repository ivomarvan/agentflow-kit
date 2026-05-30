---
apm_category: dod
apm_ref: E010.T010
apm_level: task
created_by: Planner
model: claude-opus-4-7
intended_for: Coder
created_at: 2026-05-28
updated_at: 2026-05-28
approved_by: Human
approved_at: 2026-05-28
human_decisions_at: 2026-05-28
---

# Definition of Done: E010.T010 — Package scaffolding & signals

Coder zaškrtne každý bod po jeho splnění.

## Struktura balíčku

- [x] `src/agentflow/statemachine/__init__.py` existuje a re-exportuje `EnumSignal`, `StdSignal`.
- [x] `src/agentflow/statemachine/signal.py` obsahuje `EnumSignal: TypeAlias = Enum` a `class StdSignal(EnumSignal)` se členy `ok`, `fail`, `done`.
- [x] Placeholder moduly existují s docstringem a TODO odkazem na konkrétní task:
  - [x] `state.py` (odkaz na T020)
  - [x] `context.py` (odkaz na T030)
  - [x] `vertex.py` (odkaz na T030)
  - [x] `topology.py` (odkaz na T040)
  - [x] `runner.py` (odkaz na T050)
  - [x] `hooks.py` (odkaz na T060)
- [x] `src/agentflow/statemachine/README.md` existuje (stub odkazující na brief).

## Test struktura

- [x] `src/agentflow/tests/statemachine/__init__.py` existuje.
- [x] `src/agentflow/tests/statemachine/test_signal.py` obsahuje všechny 3 testy ze spec §6.

## Top-level re-export

- [x] `src/agentflow/__init__.py` re-exportuje `EnumSignal`, `StdSignal` a obsahuje je v `__all__`.

## Dependency

- [x] `pyproject.toml` obsahuje `frozendict>=2.4` v sekci dependencies se zdůvodňujícím komentářem.

## Kvalita kódu

- [x] Všechny moduly mají modulový docstring popisující účel.
- [x] Všechny veřejné symboly mají Google-style docstring (per `10-python.mdc`).
- [x] Žádné relativní importy (`from .` / `from ..`) — jen absolutní `from src.agentflow...`.
- [x] `from __future__ import annotations` použito tam, kde to pomáhá mypy / lazy eval.

## Verifikace

- [x] Smoke test prošel:
  ```bash
  python -c "from src.agentflow.statemachine import EnumSignal, StdSignal; print(StdSignal.ok)"
  ```
  Výstup: `StdSignal.ok`.

- [x] Všech 3 testů statemachine zelených:
  ```bash
  pytest src/agentflow/tests/statemachine/
  ```

- [x] Regrese mimo `statemachine/` (T010 mění top-level `__init__.py`):
  ```bash
  pytest src/agentflow/tests/
  ```
  U ostatních tasků E010 stačí pouze `pytest src/agentflow/tests/statemachine/` (viz epic `plan.md` § Rozhodnutí).

- [x] mypy strict zelený pro statemachine moduly:
  ```bash
  mypy --strict --follow-imports=skip src/agentflow/statemachine/
  ```
  Poznámka: bez `--follow-imports=skip` mypy načte eager importy z `src/agentflow/__init__.py` a hlásí chyby mimo scope T010. Přidáno `explicit_package_bases = true` do `pyproject.toml`.

- [x] Ruff linter + formatter čisté:
  ```bash
  ruff check src/agentflow/statemachine/ src/agentflow/tests/statemachine/
  ruff format --check src/agentflow/statemachine/ src/agentflow/tests/statemachine/
  ```

## Reporting

- [x] `report.md` v tomto adresáři vypracován dle `.cursor/rules/07-project-management.mdc` (sekce 1–6: Co bylo implementováno, Vstupy a výstupy, Použité metody a rozhodnutí, Reference do kódu, Výsledek regresního testu, Definition of Done).

## Bezpečnostní zábrany

- [x] **Žádný `git commit/push`** proveden bez explicitního pokynu Human.
- [x] **Žádné mazání** souborů mimo cíl tasku.
