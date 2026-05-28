---
apm_category: task-spec
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

# Task Specification: E010.T010 — Package scaffolding & signals

## 1. Goal

Založit balíček `src/agentflow/statemachine/` se strukturou dle briefu §8, přidat `frozendict` dependency a implementovat triviální `EnumSignal` typový alias + `StdSignal` enum jako první stavební kámen, který validuje, že struktura funguje. **Žádná byznys logika** — pouze scaffolding, na kterém staví všechny další Tasky Epicu E010.

## 2. Inputs

Coder při implementaci čte tyto soubory (cesty relativní ke kořeni repozitáře):

- `src/agentflow/doc/project-progress/brief.md` — celý dokument; zejména:
  - §1.3 *Signály (směrování)* — definice `EnumSignal: TypeAlias = Enum` a `StdSignal`.
  - §8 *Navrhovaná struktura balíčku* — cílová adresářová struktura `statemachine/`.
- `src/agentflow/doc/project-progress/spec.md`:
  - TD-03 (Enum typový alias).
  - TD-13 (žádné nové dep kromě `frozendict`).
- `src/agentflow/doc/project-progress/GLOSSARY.md` — pojmy `EnumSignal`, `StdSignal`.
- `pyproject.toml` — formát závislostí, `requires-python`, `[tool.mypy]`, `[tool.pytest.ini_options]`.
- `src/agentflow/__init__.py` — vzor public re-exportů (pro inspiraci u `statemachine/__init__.py`).
- `src/agentflow/llm/__init__.py` — vzor strukturovaného modulu.
- `.cursor/rules/10-python.mdc` — Python coding standards (povinné dodržet).

## 3. Outputs

### 3.1 Nové soubory

```
src/agentflow/statemachine/
├── __init__.py                          # public re-exporty: EnumSignal, StdSignal
├── signal.py                            # EnumSignal alias + StdSignal enum
├── README.md                            # stub (rozšíří E080)
├── state.py                             # PLACEHOLDER (docstring + TODO komentář, žádný kód)
├── context.py                           # PLACEHOLDER
├── vertex.py                            # PLACEHOLDER
├── topology.py                          # PLACEHOLDER
├── runner.py                            # PLACEHOLDER
└── hooks.py                             # PLACEHOLDER

src/agentflow/tests/statemachine/
├── __init__.py
└── test_signal.py
```

### 3.2 Modifikované soubory

- `pyproject.toml` — přidat `frozendict>=2.4` (s komentářem zdůvodnění).
- `src/agentflow/__init__.py` — **povinně** přidat re-export `EnumSignal`, `StdSignal` do `__all__` (Human rozhodnutí 2026-05-28, TD-16 v `spec.md`).

### 3.3 Detaily obsahu

#### `signal.py`

```python
"""EnumSignal alias and StdSignal — routing signals for the state machine.

EnumSignal is a TypeAlias for Enum used in framework signatures (Transition, run()
return type). Concrete signal sets are user-defined Enum subclasses; StdSignal
provides the universally useful ok/fail/done set.
"""

from enum import Enum, auto
from typing import TypeAlias


EnumSignal: TypeAlias = Enum

# Pattern: Marker Type Alias — gives a domain name to a stdlib type without
# introducing a new class, enabling type-checker friendly annotations.

class StdSignal(EnumSignal):
    """Standard signals usable by any vertex; see brief §1.3."""

    ok = auto()
    fail = auto()
    done = auto()
```

#### `__init__.py` (statemachine package)

```python
"""agentflow.statemachine — declarative state graph orchestration for AI agents.

Public API grows incrementally with each Task of Epic E010 (see roadmap.md).
Current exports (after T010): EnumSignal, StdSignal.
"""

from src.agentflow.statemachine.signal import EnumSignal, StdSignal

__all__ = [
    "EnumSignal",
    "StdSignal",
]
```

#### Placeholder moduly (state.py, context.py, vertex.py, topology.py, runner.py, hooks.py)

Každý obsahuje jen modulový docstring s odkazem na příslušnou sekci briefu a TODO komentář, který Task XXX dodá obsah. Příklad pro `state.py`:

```python
"""State, StatePatch and per-field reducer dispatch.

See brief §1.1 for the design. Implementation lands in Epic E010, Task T020.
"""

# TODO(E010.T020): implement apply_patches(state, patches) with per-field reducer dispatch.
```

#### `README.md` (statemachine package)

```markdown
# agentflow.statemachine

Declarative state graph orchestration for AI agents — Bulk Synchronous Parallel
(BSP) execution model with per-field state reducers.

Status: **work in progress** (Epic E010).

See [../../doc/project-progress/brief.md](../../doc/project-progress/brief.md)
for the full design brief.
```

#### `pyproject.toml` — přidání závislosti

Lokalizovat sekci `[project]` `dependencies = [...]` (nebo `[tool.poetry.dependencies]` podle managera). Přidat:

```toml
"frozendict>=2.4",   # immutable dict for State containers; see brief §1.2 (statemachine)
```

#### `tests/statemachine/test_signal.py`

```python
"""Unit tests for EnumSignal and StdSignal."""

import pytest
from enum import Enum, auto

from src.agentflow.statemachine import EnumSignal, StdSignal


@pytest.mark.unit
class TestStdSignal:
    def test_std_signal_has_ok_fail_done_members(self) -> None:
        assert StdSignal.ok.name == "ok"
        assert StdSignal.fail.name == "fail"
        assert StdSignal.done.name == "done"

    def test_std_signal_member_is_enum_instance(self) -> None:
        # EnumSignal is a TypeAlias for Enum; runtime check uses Enum.
        assert isinstance(StdSignal.ok, Enum)

    def test_custom_signal_can_be_defined_independently(self) -> None:
        class CustomSignal(EnumSignal):
            approved = auto()
            rejected = auto()

        assert isinstance(CustomSignal.approved, Enum)
        assert CustomSignal.approved.name == "approved"
```

## 4. Context Bundle

### Read (potřebuje Coder)

| Soubor | Proč |
|--------|------|
| `src/agentflow/doc/project-progress/brief.md` | Celkový kontext + §1.3 + §8 (struktura). |
| `src/agentflow/doc/project-progress/spec.md` | TD-03, TD-13. |
| `src/agentflow/doc/project-progress/GLOSSARY.md` | Termíny. |
| `pyproject.toml` | Formát závislostí, mypy/pytest konfigurace. |
| `src/agentflow/__init__.py` | Vzor re-exportů. |
| `src/agentflow/llm/__init__.py` | Vzor modulu se sub-balíčkem. |
| `.cursor/rules/10-python.mdc` | Coding standards (dodržet doslova). |

### Do NOT modify

- `src/agentflow/llm/**`
- `src/agentflow/agents/**`
- `src/agentflow/tools/**`
- `src/agentflow/describable/**`
- `src/agentflow/doc/**` mimo vlastní task adresář (`task-010-package-scaffolding/report.md` a `dod.md` zapisuje Coder).
- `tests/` (kořenové) — testy patří do `src/agentflow/tests/statemachine/`.

### Interfaces from prior tasks

Žádné. T010 je první task projektu.

### Interfaces poskytované tímto Taskem následujícím

```python
# z src.agentflow.statemachine:
EnumSignal: TypeAlias = Enum
class StdSignal(EnumSignal): ok, fail, done
```

Všechny další tasky (T020+) mohou očekávat, že tento import funguje:
```python
from src.agentflow.statemachine import EnumSignal, StdSignal
```

## 5. Dependencies

Žádné — T010 je první task v Epicu E010.

## 6. Test Specification

Soubor `src/agentflow/tests/statemachine/test_signal.py`:

| # | Test name                                                | Co ověřuje |
|---|----------------------------------------------------------|------------|
| 1 | `test_std_signal_has_ok_fail_done_members`               | `StdSignal` má všechny 3 členy se správnými jmény. |
| 2 | `test_std_signal_member_is_enum_instance`                | Runtime check `isinstance(StdSignal.ok, Enum)`. |
| 3 | `test_custom_signal_can_be_defined_independently`        | Uživatel může nadefinovat vlastní `EnumSignal` potomka. |

**Smoke test (manuální):** spustit
```bash
python -c "from src.agentflow.statemachine import EnumSignal, StdSignal; print(StdSignal.ok)"
```
očekávaný výstup: `StdSignal.ok`.

**Regresní suite:**
```bash
pytest src/agentflow/tests/statemachine/   # default pro tasky E010
pytest src/agentflow/tests/                # navíc v T010 (mění src/agentflow/__init__.py)
mypy --strict src/agentflow/statemachine/
```
Obě musí projít zelené. U ostatních tasků E010 stačí `statemachine/` testy — viz epic `plan.md` § Rozhodnutí.

## 7. Definition of Done

Viz `dod.md` v tomto adresáři.

## 8. Recommended Coder model

**Composer-2** — strukturální task bez složité algoritmické logiky. Důležitá je správná organizace souborů a dodržení coding standards.

## 9. Poznámky pro Coder

- **Dodržuj `.cursor/rules/10-python.mdc`**: type hints všude, Google-style docstringy, absolute imports `from src.agentflow...`, `git_root_to_syspath` v entry-point skriptech.
- **`__future__ annotations`**: použít v každém modulu, kde dává smysl (mypy strict friendly, lazy evaluation type hints).
- **Žádný TODO bez issue v plain kódu** dle `01-general-programming.mdc` — výjimka: placeholder moduly v T010 mají TODO odkazující na konkrétní task (`TODO(E010.T020): ...`), což je validní stopa pro Coder navazujícího tasku.
- **Po dokončení:** vyplnit `dod.md` checklist + napsat `report.md` (struktura per `.cursor/rules/07-project-management.mdc`).
- **Nedělej git commit** — vyčkej na explicitní instrukci od Human.
