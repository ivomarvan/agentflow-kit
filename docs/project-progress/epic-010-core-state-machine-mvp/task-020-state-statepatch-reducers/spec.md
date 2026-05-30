---
apm_category: task-spec
apm_ref: E010.T020
apm_level: task
created_by: Planner
model: claude-opus-4-7
intended_for: Coder
created_at: 2026-05-28
updated_at: 2026-05-28
---

# Task Specification: E010.T020 — State, StatePatch & per-field reducery

## 1. Goal

Implementovat mechanismus per-field reducerů z briefu §1.1. Klíčová funkce `apply_patches(state, patches)`,
která pro každé pole stavu načte reducer z `Annotated[T, reducer]` anotace, postupně aplikuje příspěvky
z patchů a vrátí novou instanci stavu. Pole bez reduceru → last-writer-wins + WARNING při kolizi.
Sentinel `UNSET = object()` pro „nesetuj". Vše jako standalone funkce v `state.py` — uživatelský
`State` nedědí od frameworku (TD-14 v `spec.md`).

## 2. Inputs

- `src/agentflow/doc/project-progress/brief.md` — §1.1 (State, StatePatch, reducery) a §1.2 (imutabilní kontejnery).
- `src/agentflow/doc/project-progress/spec.md` — TD-02 (StatePatch + per-field reducery), TD-14 (`apply_patches` jako standalone funkce), TD-15.
- `src/agentflow/doc/project-progress/GLOSSARY.md` — definice Reducer, State, StatePatch.
- `src/agentflow/doc/project-progress/epic-010-core-state-machine-mvp/plan.md` — sekce T020 pro přehled.
- `src/agentflow/statemachine/signal.py` — hotový T010 výstup (pro import v testech).
- `pyproject.toml` — konfigurace mypy, pytest.
- `.cursor/rules/10-python.mdc` — Python coding standards.

## 3. Outputs

### 3.1 Modifikované soubory

- `src/agentflow/statemachine/state.py` — **kompletní implementace** (nahradit placeholder).
- `src/agentflow/statemachine/__init__.py` — přidat `apply_patches`, `UNSET` do re-exportů.

### 3.2 Nové soubory

- `src/agentflow/tests/statemachine/test_state_reducers.py` — 7 unit testů.

### 3.3 Detaily obsahu

#### `state.py` — veřejné API

```python
"""State, StatePatch and per-field reducer dispatch.

Standalone helper functions for applying patches to frozen dataclass states.
User-defined State classes remain plain frozen dataclasses — no framework
base class required (see spec.md TD-14).
"""

from __future__ import annotations

import dataclasses
import logging
from typing import Annotated, Any, Callable, TypeVar, get_type_hints, get_args, get_origin

# Sentinel — distinguishes "not set in this patch" from "explicitly set to None".
# Use as default value in StatePatch fields where None is a valid domain value.
UNSET: object = object()

_logger = logging.getLogger(__name__)

S = TypeVar("S")  # bound to frozen dataclass; mypy resolves via TypeVar with bound


def extract_reducer(annotated_type: Any) -> Callable[[Any, Any], Any] | None:
    """Return the reducer callable from an Annotated[T, reducer] type, or None.

    Args:
        annotated_type: A type annotation, potentially Annotated[T, reducer].

    Returns:
        The reducer callable if present as the first metadata argument,
        otherwise None.
    """
    ...


def apply_patches(state: S, patches: Sequence[Any]) -> S:
    """Merge a sequence of StatePatch objects into a new state instance.

    For each field:
    - If annotated with Annotated[T, reducer]: calls reducer(accumulated, new) for
      each patch that sets the field (non-None, non-UNSET).
    - If no reducer: last-writer-wins; emits WARNING when multiple patches write
      the same field with different non-None values (non-deterministic merge).
    - None in a patch field means "do not set" (skip).
    - UNSET sentinel means "do not set" (skip).

    Args:
        state: Current frozen dataclass instance.
        patches: Sequence of StatePatch-like objects (frozen dataclasses with
                 Optional fields defaulting to None).

    Returns:
        New state instance with all patch contributions merged.
        Returns the same state object when patches is empty.

    Raises:
        TypeError: If state is not a dataclass instance.
    """
    ...
```

**Implementační poznámky:**
- Použít `dataclasses.fields(state)` pro iteraci přes pole.
- `typing.get_type_hints(type(state), include_extras=True)` pro získání `Annotated` anotací.
- `typing.get_origin(hint) is Annotated` → `typing.get_args(hint)[1:]` pro metadata (reducer).
- `dataclasses.replace(state, **updates)` pro vytvoření nové instance.
- TypeVar bound: `S = TypeVar("S")` — mypy s `--strict` přijme, protože `dataclasses.replace` vrátí stejný typ.
- Human rozhodnutí (plan.md §Rozhodnutí bod 3): Coder rozhodne TypeVar bound při T020 tak, aby `--strict` vracel stejný typ stavu.

#### `__init__.py` — přidání exportů

```python
from src.agentflow.statemachine.state import apply_patches, UNSET
# přidat do __all__: "apply_patches", "UNSET"
```

#### `tests/statemachine/test_state_reducers.py`

```python
"""Unit tests for apply_patches and per-field reducer dispatch."""

import operator
import logging
import pytest
from dataclasses import dataclass
from typing import Annotated

from src.agentflow.statemachine import apply_patches, UNSET


@dataclass(frozen=True)
class MyState:
    messages: Annotated[tuple[str, ...], operator.add] = ()
    score: Annotated[float, max] = 0.0
    author: str = ""


@dataclass
class MyPatch:
    messages: tuple[str, ...] | None = None
    score: float | None = None
    author: str | None = None


@pytest.mark.unit
class TestApplyPatches:
    def test_apply_patches_uses_reducer_for_annotated_field(self) -> None:
        # operator.add on tuple concatenates contributions from two patches
        ...

    def test_apply_patches_max_reducer_keeps_higher_score(self) -> None:
        ...

    def test_apply_patches_no_reducer_last_writer_wins(self) -> None:
        ...

    def test_apply_patches_no_reducer_warns_on_collision(self, caplog) -> None:
        # caplog captures WARNING when 2 patches write the same field without reducer
        with caplog.at_level(logging.WARNING):
            ...
        assert "WARNING" in caplog.text or any(r.levelname == "WARNING" for r in caplog.records)

    def test_apply_patches_skips_none_value_in_patch(self) -> None:
        # None in patch field = "do not set"
        ...

    def test_apply_patches_returns_new_instance(self) -> None:
        # original state must not be mutated
        ...

    def test_apply_patches_empty_patch_list_returns_same_state(self) -> None:
        ...
```

## 4. Context Bundle

### Read (Coder potřebuje)

| Soubor | Proč |
|--------|------|
| `src/agentflow/doc/project-progress/brief.md` | §1.1 (reducery, apply_patches algoritmus), §1.2 (imutabilní typy). |
| `src/agentflow/doc/project-progress/spec.md` | TD-02, TD-14 (standalone funkce). |
| `src/agentflow/doc/project-progress/GLOSSARY.md` | Termíny Reducer, StatePatch. |
| `src/agentflow/statemachine/signal.py` | Vzor stylu kódu. |
| `pyproject.toml` | mypy strict, pytest konfigurace. |
| `.cursor/rules/10-python.mdc` | Coding standards. |

### Do NOT modify

- `src/agentflow/statemachine/signal.py` (T010 hotov).
- `src/agentflow/llm/**`, `src/agentflow/agents/**`, `src/agentflow/tools/**`, `src/agentflow/describable/**`.
- `src/agentflow/doc/**` mimo `task-020-state-statepatch-reducers/report.md` a `dod.md`.

### Interfaces from prior tasks

```python
# z T010 — volně k importu:
from src.agentflow.statemachine import EnumSignal, StdSignal
```

### Interfaces poskytované tímto Taskem pro T030+

```python
# z src.agentflow.statemachine:
UNSET: object                                    # sentinel pro "nesetuj"
apply_patches(state: S, patches: Sequence) -> S  # merge patchů do nového stavu
```

## 5. Dependencies

- T010 (Package scaffolding & signals) — **dokončen** ✅

## 6. Test Specification

Soubor `src/agentflow/tests/statemachine/test_state_reducers.py`:

| # | Test name | Co ověřuje |
|---|-----------|------------|
| 1 | `test_apply_patches_uses_reducer_for_annotated_field` | `operator.add` na `tuple` konkatenuje příspěvky ze dvou patchů. |
| 2 | `test_apply_patches_max_reducer_keeps_higher_score` | `max` reducer vrátí vyšší hodnotu ze dvou patchů. |
| 3 | `test_apply_patches_no_reducer_last_writer_wins` | Pole bez reduceru: poslední patch vyhrává. |
| 4 | `test_apply_patches_no_reducer_warns_on_collision` | `caplog` zachytí WARNING při 2 patchích na stejném poli bez reduceru. |
| 5 | `test_apply_patches_skips_none_value_in_patch` | `None` v patchi se ignoruje. |
| 6 | `test_apply_patches_returns_new_instance` | Původní stav nezměněn (immutability). |
| 7 | `test_apply_patches_empty_patch_list_returns_same_state` | Edge case: prázdný seznam patchů. |

**Regresní suite:**
```bash
pytest src/agentflow/tests/statemachine/
mypy --strict --follow-imports=skip src/agentflow/statemachine/
ruff check src/agentflow/statemachine/ src/agentflow/tests/statemachine/
```

## 7. Definition of Done

Viz `dod.md` v tomto adresáři.

## 8. Recommended Coder model

**claude-sonnet-4-6** — reducer dispatch je nontriviální typová introspekce (`typing.get_type_hints`, `get_args`, TypeVar bound pro mypy strict).

## 9. Poznámky pro Coder

- `typing.get_type_hints(type(state), include_extras=True)` — klíčové pro získání `Annotated` metadat.
- `get_origin(hint) is Annotated` → True pro `Annotated[T, ...]`.
- `get_args(hint)` vrací `(T, meta1, meta2, ...)` — reducer je `get_args(hint)[1]`.
- `dataclasses.replace(state, **{field_name: new_value, ...})` pro vytvoření nové instance.
- `UNSET` je modul-level singleton; test na `patch_val is UNSET or patch_val is None`.
- TypeVar `S = TypeVar("S")` bez bound je dostačující pro mypy; pokud strict neprochází, přidat `bound=Any` nebo použít `cast`.
- Po dokončení: vyplnit `dod.md` + napsat `report.md`. Bez git commitu.
