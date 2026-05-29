---
apm_category: task-report
apm_ref: E010.T020
apm_level: task
created_by: Coder
model: claude-sonnet-4-6
intended_for: Human
created_at: 2026-05-28
updated_at: 2026-05-28
---

# Task Report: E010.T020 — State, StatePatch & per-field reducery

## Co bylo implementováno

Implementován mechanismus per-field reducerů dle briefu §1.1. Klíčová funkce `apply_patches(state, patches)`
iteruje přes pole frozen dataclass stavu, extrahuje reducer z `Annotated[T, reducer]` anotací pomocí
`typing.get_type_hints(..., include_extras=True)`, a aplikuje příspěvky z patchů: pole s reducerem akumulují
hodnoty reducerem (např. `operator.add`, `max`), pole bez reduceru fungují last-writer-wins s emisí WARNING
při kolizi. Sentinel `UNSET = object()` a hodnota `None` jsou obě interpretovány jako „nesetuj toto pole".
Uživatelské `State` třídy zůstávají plain frozen dataclassy — žádná frameworková base class není vyžadována (TD-14).

## Vstupy a výstupy

- **Přečteno:**
  - `src/agentflow/doc/project-progress/brief.md` — §1.1 (State, StatePatch, reducery), §1.2 (imutabilní kontejnery)
  - `src/agentflow/doc/project-progress/epic-010-core-state-machine-mvp/task-020-state-statepatch-reducers/spec.md`
  - `src/agentflow/statemachine/signal.py` — vzor stylu kódu
  - `src/agentflow/statemachine/__init__.py` — stávající exporty
  - `.cursor/rules/10-python.mdc` — Python coding standards
- **Změněno:**
  - `src/agentflow/statemachine/state.py` — placeholder nahrazen kompletní implementací
  - `src/agentflow/statemachine/__init__.py` — přidány re-exporty `apply_patches`, `UNSET`
- **Vytvořeno:**
  - `src/agentflow/tests/statemachine/test_state_reducers.py` — 7 unit testů

## Použité metody a rozhodnutí

- **`typing.get_type_hints(type(state), include_extras=True)`** — klíčové pro získání `Annotated` metadat;
  bez `include_extras=True` by se `Annotated` wrappery ztratily a reducery by nebyly nalezeny.
- **TypeVar `S = TypeVar("S")` bez bound** — mypy strict přijímá, protože `dataclasses.replace` má
  overload `(obj: _T, **changes) -> _T`, který funguje s nebound TypeVar.
- **`# type: ignore[no-any-return]`** v `extract_reducer` — `get_args()` vrací `tuple[Any, ...]`, takže
  kandidát má typ `Any`; ignore je vědomý a dokumentovaný.
- **Optimalizace `if not updates: return state`** — pokud žádný patch nepřispěl žádnou hodnotou, vrací
  se původní objekt bez volání `dataclasses.replace`; to zachovává identitu objektu pro empty-patch-list test.
- **Kolize warning** — warning se emituje pouze pokud dva různé patchy zapisují na stejné pole **různé**
  hodnoty; zápis stejné hodnoty dvěma patchy warning nevyvolá (deterministický výsledek).
- **Test pro UNSET** — ruff hlásil F821 při použití `UNSET` jako default hodnoty v dataclass poli
  (pravděpodobně false positive s `from __future__ import annotations`); obejito pomocí
  `types.SimpleNamespace` přímo v těle testu.

## Odchylky od spec.md

- Test 5 (`test_apply_patches_skips_none_value_in_patch`) byl rozšířen o ověření `UNSET` sentinelu
  (vedle `None`) pomocí `types.SimpleNamespace`. Spec definoval pouze test pro `None`, ale UNSET byl
  importován v testovém modulu a musel být použit, aby prošel ruff check. Výsledný test je bohatší
  a lépe pokrývá specifikaci.

## Reference do kódu

- `src/agentflow/statemachine/state.py:17` — `UNSET` sentinel
- `src/agentflow/statemachine/state.py:24-42` — `extract_reducer()` helper
- `src/agentflow/statemachine/state.py:45-111` — `apply_patches()` hlavní funkce
- `src/agentflow/statemachine/__init__.py:1-24` — aktualizované re-exporty
- `src/agentflow/tests/statemachine/test_state_reducers.py:1-80` — 7 unit testů

## Výsledek regresního testu

✅ Všechny testy projdou (23/23).

- `pytest src/agentflow/tests/statemachine/ -v` → **23 passed** (16 pre-existing + 7 nových)
- `mypy --strict --follow-imports=skip src/agentflow/statemachine/` → **Success: no issues found in 8 source files**
- `ruff check + ruff format --check` → **All checks passed!**

## Definition of Done

Viz [dod.md](dod.md) — všechna kritéria ✅.
