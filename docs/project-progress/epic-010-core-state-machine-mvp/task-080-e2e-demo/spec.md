---
apm_category: task-spec
apm_ref: E010.T080
apm_level: task
created_by: Planner
model: claude-opus-4-7
intended_for: Coder
created_at: 2026-05-28
updated_at: 2026-05-28
---

# Task Specification: E010.T080 — End-to-end demo: brief §2.5 graph

## 1. Goal

Demonstrovat, že celý E010 MVP funguje jako celek. Sestavit graf z briefu §2.5
(Research → Parallel(WriteIntro, WriteBody) → Review → cyklus nebo StdEnd) z **ručně předaných
instancí**, spustit ho s `FakeLlmConnector` a `LoggingHooks`, ověřit terminaci v `StdEnd`.
Výsledkem je spustitelný demo skript a E2E integrační test.

## 2. Inputs

- `src/agentflow/doc/project-progress/brief.md` — §2.5 (kompletní příklad grafu).
- T010–T070, T050 deliverables — kompletní `statemachine/` API.
- `.cursor/rules/10-python.mdc` — coding standards.

## 3. Outputs

### 3.1 Nové soubory

```
src/examples/statemachine_demos/
├── __init__.py
└── 01_brief_example.py

src/agentflow/tests/statemachine/
└── test_e2e_brief_example.py
```

### 3.2 Modifikované soubory

- Žádné produkční moduly statemachine nejsou modifikovány.

### 3.3 Detaily obsahu

#### `src/examples/statemachine_demos/__init__.py`

Prázdný nebo minimální docstring.

#### `src/examples/statemachine_demos/01_brief_example.py`

Demo skript ilustrující graf z briefu §2.5 s fake LLM connectorem.

Struktura skriptu:
1. Definuj `DemoState` (`@dataclass(frozen=True)`) a `DemoPatch` (`@dataclass`) s poli:
   - `messages: Annotated[tuple[str, ...], operator.add] = ()` (s reducerem)
   - `iteration: int = 0`
2. Definuj vrcholy:
   - `class Research(StateVertex)` — vrátí `CustomSignal.ok`, přidá zprávu do patch.
   - `class WriteIntro(StateVertex)` — vrátí `StdSignal.done`, přidá zprávu.
   - `class WriteBody(StateVertex)` — vrátí `StdSignal.done`, přidá zprávu.
   - `class Review(StateVertex)` — vrátí `CustomSignal.approved` nebo `CustomSignal.rejected`
     podle počtu iterací (po 2 iteracích → approved).
3. Definuj `class CustomSignal(EnumSignal): ok = auto(); approved = auto(); rejected = auto()`
4. Sestav `StateGraph` s `Transition`s dle §2.5 (research → Parallel(intro, body) → review → loop/end).
5. Vytvoř `Context` s `FakeLlmConnector`.
6. Spusť `runner.run_sync(DemoState())`.
7. Vypiš finální stav a shrnutí (počet iterací, finální zprávy).

Spustitelné přes: `cd /path/to/repo && python -m src.examples.statemachine_demos.01_brief_example`

```python
# Příklad struktury (Coder doplní implementaci):

from git_root_to_syspath import agr
PROJECT_ROOT = agr()

import operator
from dataclasses import dataclass
from enum import auto
from typing import Annotated

from src.agentflow.statemachine import (
    EnumSignal, StdSignal, StateVertex, Context, StdEnd,
    Transition, Parallel, StateGraph, StateGraphRunner, apply_patches
)
from src.agentflow.statemachine.hooks import LoggingHooks
from src.agentflow.statemachine.testing import FakeLlmConnector


@dataclass(frozen=True)
class DemoState:
    messages: Annotated[tuple[str, ...], operator.add] = ()
    iteration: int = 0


@dataclass
class DemoPatch:
    messages: tuple[str, ...] | None = None
    iteration: int | None = None


class CustomSignal(EnumSignal):
    ok = auto()
    approved = auto()
    rejected = auto()


# ... vertex implementations ...
# ... StateGraph setup ...

if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO)

    connector = FakeLlmConnector()
    ctx = Context(connector=connector)
    hooks = LoggingHooks()

    # ... build graph, run_sync, print result ...
```

#### `tests/statemachine/test_e2e_brief_example.py` — 1 E2E test

```python
"""End-to-end integration test for the brief §2.5 demo graph."""

import pytest

@pytest.mark.unit
def test_brief_example_runs_to_completion() -> None:
    """Import and run the demo script, assert expected final state."""
    # Import the script's build_graph and run functions
    # OR run the demo function directly (if demo exposes a function)
    # Assert: final state has messages with content, run ended in StdEnd
    ...
```

**Tip:** Nejjednodušší implementace — demo skript definuje funkci `run_demo() -> DemoState`
kterou test importuje a volá. Test pak assertuje:
- `final_state.messages` je neprázdný tuple
- počet iterací odpovídá očekávání (Coder rozhodne)
- žádná výjimka nebyla vyhozena

## 4. Context Bundle

### Read (Coder potřebuje)

| Soubor | Proč |
|--------|------|
| `src/agentflow/doc/project-progress/brief.md` | §2.5 (příklad grafu). |
| `src/agentflow/statemachine/__init__.py` | Kompletní public API. |
| `src/agentflow/statemachine/testing/` | FakeVertex, FakeLlmConnector (T070). |
| `src/agentflow/statemachine/hooks.py` | LoggingHooks (T060). |
| `.cursor/rules/10-python.mdc` | Coding standards. |

### Do NOT modify

- Vše v `src/agentflow/statemachine/` (všechny tasky T010–T070 hotovy).
- `src/agentflow/doc/**` mimo `task-080-e2e-demo/report.md` a `dod.md`.

### Interfaces from prior tasks

```python
# Kompletní public API z __init__.py po T010-T070:
from src.agentflow.statemachine import (
    EnumSignal, StdSignal,
    apply_patches, UNSET,
    Context, StateVertex, End, StdEnd,
    Transition, Parallel, StateGraph,
    RunnerHooks, NoOpHooks, LoggingHooks,
    StateGraphRunner,
)
from src.agentflow.statemachine.testing import FakeVertex, FakeLlmConnector, make_fake_context
```

## 5. Dependencies

- T010 ✅, T020 ✅, T030 ✅, T040 ✅, T050 ✅, T060 ✅, T070 ✅

## 6. Test Specification

1 E2E test v `test_e2e_brief_example.py`.

**Regresní suite (FULL — tento task není statemachine-only):**
```bash
pytest src/agentflow/tests/statemachine/
mypy --strict --follow-imports=skip src/agentflow/statemachine/
mypy --strict --follow-imports=skip src/examples/statemachine_demos/
ruff check src/agentflow/statemachine/ src/examples/statemachine_demos/
```

## 7. Definition of Done

Viz `dod.md` v tomto adresáři.

## 8. Recommended Coder model

**Composer-2.5 Fast** — integrační úloha, kód je převážně kompozice hotových komponent.

## 9. Poznámky pro Coder

- `git_root_to_syspath` v entry-point skriptu — povinné per `10-python.mdc`.
- Demo skript musí být spustitelný jako modul: `python -m src.examples.statemachine_demos.01_brief_example`.
- `FakeLlmConnector` nepotřebuje `queue_responses()` pokud vrcholy nevolají `ctx.connector.chat()` (FakeVertex vrací předem daný signál bez LLM). Pokud ano, nastavit frontu na začátku.
- `Review` vrchol potřebuje mechanismus pro rozhodnutí po N iteracích — nejjednodušší: stav obsahuje `iteration: int` a `Review` ho čte. `DemoPatch.iteration` vrátí aktuální hodnotu+1.
- Mypy pro demo skript: `--follow-imports=skip` nechceme nutně — spíš `--ignore-missing-imports` pokud `git_root_to_syspath` způsobí problémy.
- Po dokončení: vyplnit `dod.md` + napsat `report.md`. Bez git commitu.
