---
apm_category: task-report
apm_ref: E010.T080
apm_level: task
created_by: Coder
model: claude-sonnet-4-6
intended_for: Human
created_at: 2026-05-28
updated_at: 2026-05-28
---

# Task Report: E010.T080 — End-to-end demo: brief §2.5 graph

## Co bylo implementováno

Demo skript `01_brief_example.py` sestavuje a spouští kompletní graf z briefu §2.5:
Research → Parallel(WriteIntro, WriteBody) → Review → cyklus nebo StdEnd.
`DemoState` (frozen dataclass) drží `messages` s tuple-reducerem a `iteration: int`;
`Review` schválí obsah po dvou odmitnnutích (`_APPROVE_AFTER = 2`), takže graf projde
třemi úplnými cykly a skončí v `StdEnd`. Spolu s demo skriptem jsou tři E2E testy.

## Vstupy a výstupy

- **Přečteno:** `src/agentflow/statemachine/__init__.py`, `testing/fakes.py`, `hooks.py`,
  `topology.py`, `vertex.py`, `state.py`, `context.py`, `runner.py`,
  `src/agentflow/doc/project-progress/brief.md` §2.5
- **Vytvořeno:**
  - `src/examples/statemachine_demos/__init__.py`
  - `src/examples/statemachine_demos/01_brief_example.py`
  - `src/agentflow/tests/statemachine/test_e2e_brief_example.py`
  - `src/agentflow/doc/project-progress/epic-010-core-state-machine-mvp/task-080-e2e-demo/dod.md` (vyplněn)
  - `src/agentflow/doc/project-progress/epic-010-core-state-machine-mvp/task-080-e2e-demo/report.md` (tento soubor)
- **Změněno:** žádný produkční soubor statemachine nebyl upraven.

## Použité metody a rozhodnutí

- **`CustomSignal` jako `Enum`**: spec ukázal `CustomSignal(EnumSignal)`, ale `EnumSignal`
  je `TypeAlias = Enum`, takže `class CustomSignal(Enum)` je identické a lépe čitelné
  pro mypy (přímá dědičnost z Enum, ne z TypeAlias).
- **`_APPROVE_AFTER = 2` jako modulová konstanta**: místo magické hodnoty ve třídě `Review`.
  Test importuje konstantu přes `mod._APPROVE_AFTER` pro parametrizovatelné aserce.
- **Tři testy místo jednoho**: spec požadoval minimálně 1 test; přidány 2 další (happy-path
  ověření počtu zpráv a smoke-test `build_graph()`), aby pokrývaly různé aspekty E2E.
- **`importlib.import_module()`** v testech místo přímého importu: název modulu začíná
  číslicí (`01_...`), takže `import` syntaxí by selhal — `importlib` toto zvládne.
- **`src/examples/__init__.py`** nebyl nutný: Python 3.3+ namespace packages umožňují
  `src.examples` fungovat bez `__init__.py`; pouze `statemachine_demos/__init__.py` byl vytvořen.

## Odchylky od spec.md

- **mypy `--follow-imports=skip src/examples/statemachine_demos/`** selže s 5 chybami:
  `git_root_to_syspath` nemá stubs (`import-untyped`) a `StateVertex` se stane `Any`
  (všechny závislosti jsou přeskočeny), takže subclassing generuje `[misc]` chyby.
  Toto je přesně situace předvídaná v spec.md §9 (poznámky pro Coder). DoD mypy check
  se vztahuje pouze na `src/agentflow/statemachine/`, který zůstává 100% zelený.
  Demo skript je typově správný; omezení je způsobeno architekturou `--follow-imports=skip`.

## Reference do kódu

- `src/examples/statemachine_demos/01_brief_example.py:43-60` — `DemoState`, `DemoPatch`
- `src/examples/statemachine_demos/01_brief_example.py:63-67` — `CustomSignal`
- `src/examples/statemachine_demos/01_brief_example.py:70-147` — vertex implementace
- `src/examples/statemachine_demos/01_brief_example.py:150-175` — `build_graph()`, `run_demo()`
- `src/agentflow/tests/statemachine/test_e2e_brief_example.py:1-57` — E2E testy

## Výsledek regresního testu

✅ Všechny testy projdou (44/44).

```
============================= 44 passed in 0.29s ===============================
```

Nové testy: `test_brief_example_runs_to_completion`, `test_brief_example_message_count_matches_cycles`,
`test_brief_example_build_graph_returns_state_graph`.

## Definition of Done

Viz [dod.md](dod.md) — všechna kritéria ✅.
